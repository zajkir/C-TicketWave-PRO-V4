"""Secure Google OAuth sign-in and invite-only Google registration.

Uses OAuth authorization code + PKCE, a state cookie, Google-signed OpenID ID tokens
and an exact invite-email match. No Google access/refresh tokens are stored.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import timedelta
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from google.auth.transport.requests import Request as GoogleCertRequest
from google.oauth2 import id_token as google_id_token

GOOGLE_STATE_COOKIE = 'ctw_google_oauth'
GOOGLE_AUTHORIZE = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN = 'https://oauth2.googleapis.com/token'
OAUTH_TTL_SECONDS = 600


def google_config():
    client_id = os.getenv('CTW_GOOGLE_CLIENT_ID', '').strip()
    client_secret = os.getenv('CTW_GOOGLE_CLIENT_SECRET', '').strip()
    base = os.getenv('CTW_PUBLIC_BASE_URL', '').strip().rstrip('/')
    if not client_id or not client_secret or not base:
        return None
    parsed = urlparse(base)
    if parsed.query or parsed.fragment or parsed.path not in ('', '/') or not parsed.hostname:
        return None
    local_host = parsed.hostname in ('localhost', '127.0.0.1', '::1')
    if parsed.scheme != 'https' and not (local_host and parsed.scheme == 'http'):
        return None
    return {
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': base + '/api/auth/google/callback',
    }


def install_google_auth(app, *, db, fetch, auth, issue_session, set_session_cookie,
                        log, timestamp, utcnow, hasher, session_cookie,
                        secure_cookie):
    """Install routes after the existing application and its database are initialized."""
    with db(write=True) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS google_identities (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                google_sub TEXT NOT NULL UNIQUE,
                email_at_link TEXT NOT NULL,
                linked_at TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS google_oauth_pending (
                state_hash TEXT PRIMARY KEY,
                mode TEXT NOT NULL CHECK(mode IN ('login','invite','link')),
                nonce TEXT NOT NULL,
                code_verifier TEXT NOT NULL,
                user_id INTEGER REFERENCES users(id),
                session_hash TEXT,
                invite_hash TEXT,
                expires_at TEXT NOT NULL
            )
        ''')

    def google_linked(user_id):
        return bool(fetch('SELECT user_id FROM google_identities WHERE user_id=?',
                          (user_id,), first=True))

    def google_error(reason):
        # Never include secrets, token codes or provider responses in redirect URLs.
        return RedirectResponse('/?google_error=' + reason, status_code=303)

    @app.get('/api/auth/google/start')
    def google_start(request: Request, mode: str = 'login', invite: str = ''):
        cfg = google_config()
        if not cfg:
            raise HTTPException(503, 'Google sign-in is not configured by the server administrator.')
        if mode not in ('login', 'invite', 'link'):
            raise HTTPException(422, 'Unknown Google login mode.')
        member_id = None
        session_hash = None
        invite_hash = None
        if mode == 'link':
            member = auth(request)
            member_id = member['id']
            if google_linked(member_id):
                raise HTTPException(409, 'Google is already linked to this member account.')
            session = request.cookies.get(session_cookie, '')
            session_hash = hashlib.sha256(session.encode()).hexdigest()
        elif mode == 'invite':
            if not invite or len(invite) > 300:
                raise HTTPException(400, 'A valid team invitation is required.')
            invite_hash = hashlib.sha256(invite.encode()).hexdigest()
            valid_invite = fetch('''
                SELECT id FROM invites WHERE token_hash=? AND used_at IS NULL
                AND expires_at>?''', (invite_hash, timestamp()), first=True)
            if not valid_invite:
                raise HTTPException(403, 'Your invitation is invalid or expired.')
        elif not fetch('SELECT id FROM users LIMIT 1', first=True):
            raise HTTPException(403, 'The administrator must create the workspace first.')

        state = secrets.token_urlsafe(40)
        nonce = secrets.token_urlsafe(36)
        code_verifier = secrets.token_urlsafe(64)
        challenge = hashlib.sha256(code_verifier.encode('ascii')).digest()
        import base64
        challenge = base64.urlsafe_b64encode(challenge).rstrip(b'=').decode('ascii')
        state_hash = hashlib.sha256(state.encode('ascii')).hexdigest()
        with db(write=True) as conn:
            conn.execute('DELETE FROM google_oauth_pending WHERE expires_at < ?', (timestamp(),))
            conn.execute('''INSERT INTO google_oauth_pending
                (state_hash,mode,nonce,code_verifier,user_id,session_hash,invite_hash,expires_at)
                VALUES (?,?,?,?,?,?,?,?)''',
                (state_hash, mode, nonce, code_verifier, member_id, session_hash,
                 invite_hash, (utcnow() + timedelta(seconds=OAUTH_TTL_SECONDS)).isoformat()))

        params = {
            'client_id': cfg['client_id'],
            'redirect_uri': cfg['redirect_uri'],
            'response_type': 'code',
            'scope': 'openid email profile',
            'state': state,
            'nonce': nonce,
            'code_challenge': challenge,
            'code_challenge_method': 'S256',
            'prompt': 'select_account',
        }
        response = RedirectResponse(GOOGLE_AUTHORIZE + '?' + urlencode(params), status_code=302)
        response.set_cookie(
            GOOGLE_STATE_COOKIE, state, path='/api/auth/google',
            max_age=OAUTH_TTL_SECONDS, httponly=True, samesite='lax',
            secure=secure_cookie
        )
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/api/auth/google/callback')
    def google_callback(request: Request, state: str = '', code: str = '',
                        error: str = ''):
        cfg = google_config()
        if not cfg:
            return google_error('not-configured')
        browser_state = request.cookies.get(GOOGLE_STATE_COOKIE, '')
        if not state or len(state) > 250 or not browser_state or not hmac.compare_digest(state, browser_state):
            return google_error('state')
        state_hash = hashlib.sha256(state.encode('ascii')).hexdigest()
        with db(write=True) as conn:
            pending_row = conn.execute('SELECT * FROM google_oauth_pending WHERE state_hash=? AND expires_at>?',
                                       (state_hash, timestamp())).fetchone()
            conn.execute('DELETE FROM google_oauth_pending WHERE state_hash=?', (state_hash,))
            pending = dict(pending_row) if pending_row else None

        if not pending:
            return google_error('expired')
        if error:
            return google_error('cancelled')
        if not code or len(code) > 4096:
            return google_error('invalid-response')

        try:
            with httpx.Client(timeout=15.0) as client:
                token_response = client.post(GOOGLE_TOKEN, data={
                    'code': code,
                    'client_id': cfg['client_id'],
                    'client_secret': cfg['client_secret'],
                    'redirect_uri': cfg['redirect_uri'],
                    'grant_type': 'authorization_code',
                    'code_verifier': pending['code_verifier'],
                })
                token_response.raise_for_status()
                raw_token = token_response.json().get('id_token')
            if not isinstance(raw_token, str):
                return google_error('invalid-token')
            claims = google_id_token.verify_oauth2_token(raw_token, GoogleCertRequest(), cfg['client_id'])
            if claims.get('iss') not in ('accounts.google.com', 'https://accounts.google.com'):
                return google_error('invalid-issuer')
            if claims.get('nonce') != pending['nonce'] or claims.get('email_verified') is not True:
                return google_error('unverified')
            subject = claims.get('sub', '')
            email = str(claims.get('email') or '').strip().lower()
            display_name = str(claims.get('name') or email.split('@')[0])[:100]
            if not subject or len(subject) > 255 or not email or len(email) > 200:
                return google_error('invalid-profile')
        except (httpx.HTTPError, ValueError, KeyError, TypeError, Exception):
            # Do not reflect provider errors or sensitive identifiers to the client.
            return google_error('provider')

        try:
            if pending['mode'] == 'login':
                identity = fetch('''
                    SELECT u.id, u.enabled FROM google_identities g
                    JOIN users u ON u.id=g.user_id WHERE g.google_sub=?
                ''', (subject,), first=True)
                if not identity or not identity['enabled']:
                    return google_error('not-linked')
                user_id = identity['id']

            elif pending['mode'] == 'link':
                user_id = pending['user_id']
                # A pending link must originate from a session that is still valid.
                session_active = fetch('''
                    SELECT 1 AS ok FROM sessions s JOIN users u ON u.id=s.user_id
                    WHERE s.id_hash=? AND s.user_id=? AND s.expires_at>?
                    AND u.enabled=1
                ''', (pending['session_hash'], user_id, timestamp()), first=True)
                user = fetch('SELECT id,email FROM users WHERE id=? AND enabled=1', (user_id,), first=True)
                if not session_active or not user or user['email'].lower() != email:
                    return google_error('account-mismatch')
                with db(write=True) as conn:
                    conn.execute('''INSERT INTO google_identities (user_id,google_sub,email_at_link,linked_at)
                         VALUES (?,?,?,?)''', (user_id, subject, email, timestamp()))
                    log(conn, user_id, 'auth.google_linked', 'user', user_id)
                response = RedirectResponse('/?google=linked#account', status_code=303)
                response.delete_cookie(GOOGLE_STATE_COOKIE, path='/api/auth/google')
                return response

            else:
                with db(write=True) as conn:
                    inv = conn.execute('''
                        SELECT * FROM invites
                        WHERE token_hash=? AND used_at IS NULL AND expires_at>?
                    ''', (pending['invite_hash'], timestamp())).fetchone()
                    if not inv or inv['email'].strip().lower() != email:
                        return google_error('invite-email-mismatch')
                    existing = conn.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
                    if existing:
                        return google_error('already-registered')
                    # The account is Google-only until a reset password is explicitly issued.
                    inaccessible_password = hasher.hash(secrets.token_urlsafe(52))
                    created = conn.execute('''
                        INSERT INTO users(email,name,password_hash,role,created_at)
                        VALUES (?,?,?,?,?)
                    ''', (email, display_name, inaccessible_password, inv['role'], timestamp()))
                    user_id = created.lastrowid
                    conn.execute('''INSERT INTO google_identities (user_id,google_sub,email_at_link,linked_at)
                        VALUES (?,?,?,?)''', (user_id, subject, email, timestamp()))
                    conn.execute('UPDATE invites SET used_at=? WHERE id=?',
                                 (timestamp(), inv['id']))
                    log(conn, user_id, 'team.invite_google_accepted', 'user', user_id)

            session, _csrf = issue_session(request, user_id)
            with db(write=True) as conn:
                conn.execute('UPDATE users SET last_login=? WHERE id=?', (timestamp(), user_id))
                log(conn, user_id, 'auth.google_login', 'user', user_id)
            response = RedirectResponse('/?google=success#dashboard', status_code=303)
            set_session_cookie(response, session)
            response.delete_cookie(GOOGLE_STATE_COOKIE, path='/api/auth/google')
            return response
        except sqlite3.IntegrityError:
            return google_error('already-linked')

    return {'enabled': lambda: bool(google_config()), 'linked': google_linked}
