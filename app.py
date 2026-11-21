"""Ceyrl — private-by-design, per-user ticket inventory application.

Each authenticated account is mapped server-side to its own SQLite database and
encrypted PDF vault. Cross-user ticket IDs are not meaningful outside their owner DB.
Public hosting requires SMTP email verification (or verified Google OpenID Connect).
"""
from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import smtplib
import sqlite3
import threading
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode, urlsplit

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Query
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get('CTW_DATA_DIR', BASE / 'data')).expanduser().resolve()
DATA.mkdir(parents=True, exist_ok=True)
PERSONAL = DATA / 'users'
PERSONAL.mkdir(parents=True, exist_ok=True)
AUTH_DB = DATA / 'identity.sqlite3'
BOOTSTRAP = os.environ.get('CTW_PUBLIC_BASE_URL', '').strip().rstrip('/')
GOOGLE_CLIENT_ID = os.environ.get('CTW_GOOGLE_CLIENT_ID', '').strip()
GOOGLE_CLIENT_SECRET = os.environ.get('CTW_GOOGLE_CLIENT_SECRET', '').strip()
SECURE_COOKIES = os.environ.get('CTW_SECURE_COOKIES') == '1'
SMTP_HOST = os.environ.get('CTW_SMTP_HOST', '').strip()
SMTP_PORT = int(os.environ.get('CTW_SMTP_PORT', '587'))
SMTP_USER = os.environ.get('CTW_SMTP_USER', '').strip()
SMTP_PASSWORD = os.environ.get('CTW_SMTP_PASSWORD', '')
SMTP_FROM = os.environ.get('CTW_SMTP_FROM', '').strip()
SMTP_TLS = os.environ.get('CTW_SMTP_TLS', 'starttls')
# Explicitly opt into development token echo; never enable this on public hosting.
DEV_TOKENS = (os.environ.get('CTW_LOCAL_DEV_TOKENS') == '1' and not SECURE_COOKIES
              and urlsplit(BOOTSTRAP).hostname in ('localhost', '127.0.0.1'))
PH = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
LOGIN_COOKIE = 'ctw_v5_session'
GOOGLE_COOKIE = 'ctw_google_state'
SESSION_HOURS = 12
LOCK = threading.RLock()
CURRENCIES = {'EUR', 'USD', 'GBP', 'CZK', 'PLN', 'CHF'}
AMOUNT_MAX = 100_000_000


def now() -> datetime:
    return datetime.now(timezone.utc)


def stamp() -> str:
    return now().isoformat()


def plus(minutes=0, hours=0) -> str:
    return (now() + timedelta(minutes=minutes, hours=hours)).isoformat()


def digest(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def safe_email(value: str) -> str:
    value = (value or '').strip().lower()
    if len(value) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
        raise HTTPException(422, 'Enter a valid email address.')
    return value


def clean(value: str, max_size: int = 255, required: bool = True) -> str:
    v = str(value or '').strip()
    if len(v) > max_size or (required and not v):
        raise HTTPException(422, 'Missing or too long text field.')
    return v


def password_policy(pw: str) -> None:
    if len(pw) < 12 or len(pw) > 200 or not any(x.isdigit() for x in pw) or not any(x.isalpha() for x in pw):
        raise HTTPException(422, 'Use at least 12 characters including letters and numbers.')


def cents(value: Any) -> int:
    try:
        v = Decimal(str(value))
        if not v.is_finite() or v < 0 or v > AMOUNT_MAX:
            raise InvalidOperation()
        return int((v * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(422, 'Enter a valid, non-negative monetary amount.')


def currency(value: str) -> str:
    v = (value or 'EUR').strip().upper()
    if v not in CURRENCIES:
        raise HTTPException(422, 'Unsupported currency.')
    return v


def date_utc(value: str) -> str:
    try:
        d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if d.tzinfo is None:
            raise ValueError('timezone missing')
        return d.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        raise HTTPException(422, 'Provide a date and timezone offset.')


@contextmanager
def connection(path: Path, write: bool = False):
    with LOCK:
        db = sqlite3.connect(path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=30000')
        try:
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db
            db.commit()
        except Exception:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()


def select(db, sql: str, params=(), one: bool = False):
    rows = db.execute(sql, params)
    if one:
        row = rows.fetchone()
        return dict(row) if row else None
    return [dict(x) for x in rows.fetchall()]


def init_identity():
    with sqlite3.connect(AUTH_DB) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, email TEXT UNIQUE COLLATE NOCASE NOT NULL,
            display_name TEXT NOT NULL, password_hash TEXT, verified INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, last_login TEXT
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            csrf TEXT NOT NULL, expires_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_user_sessions ON sessions(user_id);
        CREATE TABLE IF NOT EXISTS verification_tokens (
            token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            purpose TEXT NOT NULL, expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS google_links (
            google_sub TEXT PRIMARY KEY, user_id TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            email_at_link TEXT NOT NULL, linked_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS google_pending (
            state_hash TEXT PRIMARY KEY, nonce TEXT NOT NULL, verifier TEXT NOT NULL,
            mode TEXT NOT NULL, user_id TEXT, session_hash TEXT,
            expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS auth_attempts (
            bucket TEXT PRIMARY KEY, failures INTEGER NOT NULL, window_end TEXT NOT NULL
        );
        ''')


def storage_dir(uid: str) -> Path:
    # Path comes *only* from the authenticated server-owned UUID, never a request parameter.
    if not re.fullmatch(r'[0-9a-f]{32}', uid):
        raise HTTPException(500, 'Invalid account storage identifier.')
    p = PERSONAL / uid
    p.mkdir(parents=True, exist_ok=True)
    (p / 'vault').mkdir(exist_ok=True)
    return p


def init_user_db(uid: str) -> Path:
    p = storage_dir(uid) / 'inventory.sqlite3'
    with sqlite3.connect(p) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA foreign_keys=ON')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY, title TEXT NOT NULL, starts_at TEXT NOT NULL,
            venue TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '',
            country TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT 'Concert',
            notes TEXT NOT NULL DEFAULT '', archived INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_events_dates ON events(starts_at);
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES events(id),
            provider TEXT NOT NULL DEFAULT '', ticket_type TEXT NOT NULL DEFAULT 'E-Ticket',
            section TEXT NOT NULL DEFAULT '', row_label TEXT NOT NULL DEFAULT '',
            seats TEXT NOT NULL DEFAULT '', quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 1000),
            sold_quantity INTEGER NOT NULL DEFAULT 0 CHECK(sold_quantity BETWEEN 0 AND quantity),
            purchase_cents INTEGER NOT NULL DEFAULT 0, currency TEXT NOT NULL DEFAULT 'EUR',
            notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ticket_event ON tickets(event_id);
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
            filename TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
            sha256 TEXT NOT NULL, size INTEGER NOT NULL, created_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_pdf_for_lot ON attachments(ticket_id, sha256);
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id),
            marketplace TEXT NOT NULL DEFAULT 'viagogo', external_id TEXT NOT NULL DEFAULT '',
            price_cents INTEGER NOT NULL, currency TEXT NOT NULL DEFAULT 'EUR',
            status TEXT NOT NULL DEFAULT 'draft', notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id),
            listing_id INTEGER REFERENCES listings(id), quantity INTEGER NOT NULL CHECK(quantity > 0),
            revenue_cents INTEGER NOT NULL, fee_cents INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'EUR', sold_at TEXT NOT NULL,
            channel TEXT NOT NULL DEFAULT '', reference TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sales_dates ON sales(sold_at);
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY, event_id INTEGER REFERENCES events(id),
            title TEXT NOT NULL, amount_cents INTEGER NOT NULL,
            currency TEXT NOT NULL DEFAULT 'EUR', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY, action TEXT NOT NULL, resource TEXT NOT NULL,
            resource_id INTEGER NOT NULL, created_at TEXT NOT NULL
        );
        ''')
    return p


def personal_key(uid: str) -> Fernet:
    folder = storage_dir(uid)
    file = folder / '.encryption_key'
    try:
        with file.open('xb') as stream:
            os.chmod(file, 0o600)
            stream.write(Fernet.generate_key())
    except FileExistsError:
        pass
    return Fernet(file.read_bytes().strip())


def log(db, action: str, resource: str, rid: int):
    db.execute('INSERT INTO audit(action,resource,resource_id,created_at) VALUES (?,?,?,?)',
               (action,resource,rid,stamp()))


init_identity()


@asynccontextmanager
async def lifespan(_app):
    yield


app = FastAPI(title='Ceyrl', version='5.0.0', docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount('/static', StaticFiles(directory=BASE / 'static'), name='static')


@app.middleware('http')
async def headers(request: Request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; img-src 'self' data:; font-src 'self'; "
        "style-src 'self'; script-src 'self'; connect-src 'self'; "
        "form-action 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
    )
    if SECURE_COOKIES:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


def enforce_origin(request: Request):
    origin = request.headers.get('origin')
    if not origin:
        return
    allowed = {BOOTSTRAP} if BOOTSTRAP else set()
    # For reverse-proxy setups, exact public origin must be configured.
    allowed.add(str(request.base_url).rstrip('/'))
    if origin not in allowed:
        raise HTTPException(403, 'Origin not allowed.')


def session_cookie(response: Response, token: str):
    response.set_cookie(LOGIN_COOKIE, token, secure=SECURE_COOKIES, httponly=True,
                        samesite='lax', max_age=SESSION_HOURS * 3600, path='/')


def create_session(uid: str):
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(30)
    with connection(AUTH_DB, True) as db:
        db.execute('DELETE FROM sessions WHERE expires_at < ?', (stamp(),))
        db.execute('INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES (?,?,?,?)',
                   (digest(token), uid, csrf, plus(hours=SESSION_HOURS)))
        db.execute('UPDATE users SET last_login=? WHERE id=?', (stamp(),uid))
    return token, csrf


def require_user(request: Request, write: bool = False):
    if write:
        enforce_origin(request)
    token = request.cookies.get(LOGIN_COOKIE,'')
    if not token or len(token) > 250:
        raise HTTPException(401, 'Please sign in.')
    with connection(AUTH_DB) as db:
        user = select(db, '''SELECT u.id, u.email, u.display_name, u.verified, u.enabled, s.csrf
            FROM sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=? AND s.expires_at>?''', (digest(token), stamp()), True)
    if not user or not user['enabled'] or not user['verified']:
        raise HTTPException(401, 'Your session has expired.')
    if write and not hmac.compare_digest(request.headers.get('x-csrf-token', ''), user['csrf']):
        raise HTTPException(403, 'Invalid CSRF token.')
    return user


def user_db(request: Request, write: bool = False):
    user = require_user(request, write)
    return user, init_user_db(user['id'])


def oauth_enabled() -> bool:
    parsed = urlsplit(BOOTSTRAP) if BOOTSTRAP else None
    if not parsed or not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return False
    loopback = parsed.hostname in ('127.0.0.1', 'localhost')
    return bool(parsed.hostname and not parsed.path.strip('/') and not parsed.query and not parsed.fragment and
                (parsed.scheme == 'https' or (loopback and parsed.scheme == 'http')) and
                (loopback or SECURE_COOKIES))


def email_enabled() -> bool:
    return bool(SMTP_HOST and SMTP_FROM and BOOTSTRAP)


def email_link(to: str, subject: str, message: str):
    if not email_enabled():
        raise HTTPException(503, 'Email registration requires SMTP configuration. You can use Google sign-in instead.')
    mail = EmailMessage()
    mail['From'], mail['To'], mail['Subject'] = SMTP_FROM, to, subject
    mail.set_content(message)
    try:
        if SMTP_TLS == 'ssl':
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
        with server:
            if SMTP_TLS == 'starttls':
                server.starttls()
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(mail)
    except (OSError, smtplib.SMTPException):
        raise HTTPException(503, 'Could not send the verification email. Contact the administrator.')


def throttle(bucket: str, success: bool = False):
    bucket = digest(bucket)[:35]
    with connection(AUTH_DB, True) as db:
        row = select(db,'SELECT * FROM auth_attempts WHERE bucket=?',(bucket,),True)
        if success:
            db.execute('DELETE FROM auth_attempts WHERE bucket=?',(bucket,))
            return
        if row and row['window_end'] > stamp() and row['failures'] >= 8:
            raise HTTPException(429, 'Too many attempts. Try later.')
        if not row or row['window_end'] < stamp():
            db.execute('REPLACE INTO auth_attempts VALUES (?,?,?)', (bucket, 1, plus(minutes=15)))
        else:
            db.execute('UPDATE auth_attempts SET failures=failures+1 WHERE bucket=?',(bucket,))


class Register(BaseModel):
    email: str
    name: str = Field(min_length=2,max_length=100)
    password: str = Field(min_length=12,max_length=200)


class Login(BaseModel):
    email: str
    password: str


class Verify(BaseModel):
    token: str


class Forgot(BaseModel):
    email: str


class Reset(BaseModel):
    token: str
    password: str


@app.get('/')
def home():
    return FileResponse(BASE / 'static' / 'index.html')


@app.get('/health')
def health():
    return {'status':'ok','service':'Ceyrl'}


@app.get('/api/auth/state')
def state(request: Request):
    try:
        user = require_user(request)
        return {'authenticated':True,'user':{k:user[k] for k in ('id','email','display_name')},
                'csrf':user['csrf'],'google_enabled':oauth_enabled(), 'email_enabled':email_enabled()}
    except HTTPException:
        return {'authenticated':False,'user':None, 'google_enabled':oauth_enabled(), 'email_enabled':email_enabled()}


@app.post('/api/auth/register')
def register(payload: Register, request: Request):
    enforce_origin(request)
    if not email_enabled() and not DEV_TOKENS:
        raise HTTPException(503, 'Email registration is not enabled; use Google sign-in or ask the administrator.')
    email = safe_email(payload.email)
    password_policy(payload.password)
    throttle('register-ip:' + (request.client.host if request.client else 'unknown'))
    throttle('register:' + (request.client.host if request.client else '') + ':' + email)
    user_id, token = uuid.uuid4().hex, secrets.token_urlsafe(40)
    with connection(AUTH_DB, True) as db:
        try:
            db.execute('INSERT INTO users(id,email,display_name,password_hash,verified,created_at) VALUES(?,?,?,?,0,?)',
                       (user_id, email, clean(payload.name,100), PH.hash(payload.password), stamp()))
        except sqlite3.IntegrityError:
            # Do not reveal which emails are registered.
            return {'ok':True,'message':'If registration is possible, you will receive a verification email.'}
        db.execute('INSERT INTO verification_tokens VALUES (?,?,?,?)',
                   (digest(token),user_id,'verify',plus(minutes=60)))
    if DEV_TOKENS:
        # Available only when explicit local-development flag is enabled.
        return {'ok':True,'dev_verification_token':token,'message':'Development account created.'}
    email_link(email, 'Verify your Ceyrl account',
               'Welcome to Ceyrl! Verify your account using this link:\n\n' +
               BOOTSTRAP + '/?verify=' + token + '\n\nThis link expires in 60 minutes.')
    return {'ok':True,'message':'Check your email for a verification link.'}


@app.post('/api/auth/verify')
def verify_email(payload: Verify, request: Request):
    enforce_origin(request)
    if not payload.token or len(payload.token) > 250:
        raise HTTPException(400,'Invalid verification token.')
    with connection(AUTH_DB,True) as db:
        row = select(db,'''SELECT user_id FROM verification_tokens
            WHERE token_hash=? AND purpose='verify' AND expires_at>?''',(digest(payload.token),stamp()),True)
        if not row:
            raise HTTPException(400,'The verification link has expired or is invalid.')
        db.execute('UPDATE users SET verified=1 WHERE id=?',(row['user_id'],))
        db.execute('DELETE FROM verification_tokens WHERE token_hash=?',(digest(payload.token),))
    init_user_db(row['user_id'])
    return {'ok':True,'message':'Verified. You can now sign in.'}


@app.post('/api/auth/login')
def login(payload: Login, request: Request):
    enforce_origin(request)
    email=safe_email(payload.email)
    bucket='login:'+(request.client.host if request.client else '')+':'+email
    throttle(bucket)
    with connection(AUTH_DB) as db:
        user=select(db,'SELECT * FROM users WHERE email=?',(email,),True)
    okay=False
    if user and user['enabled'] and user['verified'] and user['password_hash']:
        try:
            okay=PH.verify(user['password_hash'],payload.password)
        except (VerifyMismatchError,VerificationError):
            pass
    if not okay:
        raise HTTPException(401,'Invalid login or unverified email.')
    throttle(bucket,True)
    token,csrf=create_session(user['id'])
    response=JSONResponse({'ok':True,'csrf':csrf})
    session_cookie(response,token)
    return response


@app.post('/api/auth/logout')
def logout(request: Request):
    user=require_user(request, True)
    with connection(AUTH_DB,True) as db:
        db.execute('DELETE FROM sessions WHERE token_hash=?',(digest(request.cookies[LOGIN_COOKIE]),))
    response=JSONResponse({'ok':True})
    response.delete_cookie(LOGIN_COOKIE,path='/')
    return response


@app.post('/api/auth/forgot')
def forgot(payload: Forgot, request: Request):
    enforce_origin(request)
    if not email_enabled():
        raise HTTPException(503,'Password reset emails are not configured.')
    email=safe_email(payload.email)
    throttle('forgot-ip:' + (request.client.host if request.client else 'unknown'))
    throttle('forgot:'+email)
    with connection(AUTH_DB) as db:
        user=select(db,'SELECT id FROM users WHERE email=? AND verified=1 AND password_hash IS NOT NULL',(email,),True)
    if user:
        token=secrets.token_urlsafe(40)
        with connection(AUTH_DB,True) as db:
            db.execute('INSERT INTO verification_tokens VALUES (?,?,?,?)',
                       (digest(token),user['id'],'reset',plus(minutes=30)))
        email_link(email,'Reset Ceyrl password',
                   'Reset your password with the following link (30 minutes):\n\n'+
                   BOOTSTRAP+'/?reset='+token)
    return {'ok':True,'message':'If your account supports password reset, an email has been sent.'}


@app.post('/api/auth/reset')
def reset(payload: Reset,request: Request):
    enforce_origin(request)
    password_policy(payload.password)
    with connection(AUTH_DB,True) as db:
        row=select(db,'SELECT user_id FROM verification_tokens WHERE token_hash=? AND purpose=? AND expires_at>?',
                   (digest(payload.token),'reset',stamp()),True)
        if not row:
            raise HTTPException(400,'Password reset link has expired.')
        db.execute('UPDATE users SET password_hash=? WHERE id=?',(PH.hash(payload.password),row['user_id']))
        db.execute('DELETE FROM verification_tokens WHERE token_hash=?',(digest(payload.token),))
        db.execute('DELETE FROM sessions WHERE user_id=?',(row['user_id'],))
    return {'ok':True}


# --- Google OpenID Connect: state + nonce + PKCE, server-side verified ID tokens ---


def google_url() -> str:
    return BOOTSTRAP+'/api/auth/google/callback'


@app.get('/api/auth/google/start')
def google_start(request: Request, mode: str='signin'):
    if not oauth_enabled():
        raise HTTPException(503, 'Google sign-in is not configured.')
    if mode not in ('signin','link'):
        raise HTTPException(422,'Invalid Google flow.')
    user_id=session_hash=None
    if mode=='link':
        user=require_user(request)
        user_id=user['id']
        session_hash=digest(request.cookies[LOGIN_COOKIE])
    state,nonce,verifier=secrets.token_urlsafe(40),secrets.token_urlsafe(40),secrets.token_urlsafe(64)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    with connection(AUTH_DB,True) as db:
        db.execute('DELETE FROM google_pending WHERE expires_at<?',(stamp(),))
        db.execute('INSERT INTO google_pending VALUES (?,?,?,?,?,?,?)',
                   (digest(state),nonce,verifier,mode,user_id,session_hash,plus(minutes=10)))
    params={'client_id':GOOGLE_CLIENT_ID,'redirect_uri':google_url(), 'scope':'openid email profile',
            'response_type':'code','state':state,'nonce':nonce,'code_challenge':challenge,
            'code_challenge_method':'S256','prompt':'select_account'}
    response=RedirectResponse('https://accounts.google.com/o/oauth2/v2/auth?'+urlencode(params),status_code=302)
    response.set_cookie(GOOGLE_COOKIE,state,secure=SECURE_COOKIES,httponly=True,samesite='lax',
                        max_age=600,path='/api/auth/google')
    return response


def oauth_problem(slug: str):
    response=RedirectResponse('/?google_error='+slug,status_code=303)
    response.delete_cookie(GOOGLE_COOKIE,path='/api/auth/google')
    return response


@app.get('/api/auth/google/callback')
def google_callback(request: Request, state: str='',code: str='',error: str=''):
    if not oauth_enabled():
        return oauth_problem('configuration')
    browser_state=request.cookies.get(GOOGLE_COOKIE,'')
    if not state or len(state)>200 or not browser_state or not hmac.compare_digest(state,browser_state):
        return oauth_problem('state')
    with connection(AUTH_DB,True) as db:
        row=select(db,'SELECT * FROM google_pending WHERE state_hash=? AND expires_at>?',
                   (digest(state),stamp()),True)
        db.execute('DELETE FROM google_pending WHERE state_hash=?',(digest(state),))
    if not row or error or not code or len(code)>4096:
        return oauth_problem('cancelled')
    try:
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2 import id_token as google_id_token
        with httpx.Client(timeout=15) as client:
            r=client.post('https://oauth2.googleapis.com/token',data={
                'code':code, 'client_id':GOOGLE_CLIENT_ID,'client_secret':GOOGLE_CLIENT_SECRET,
                'redirect_uri':google_url(),'grant_type':'authorization_code',
                'code_verifier':row['verifier']})
            r.raise_for_status()
            raw=r.json()['id_token']
        profile=google_id_token.verify_oauth2_token(raw,GoogleRequest(),GOOGLE_CLIENT_ID)
        if (profile.get('iss') not in ('accounts.google.com','https://accounts.google.com') or
                profile.get('nonce') != row['nonce'] or profile.get('email_verified') is not True):
            return oauth_problem('identity')
        subject=str(profile.get('sub') or '')
        email=safe_email(str(profile.get('email') or ''))
        name=clean(str(profile.get('name') or email.split('@')[0]),100)
        if not subject or len(subject)>255:
            return oauth_problem('identity')
    except Exception:
        return oauth_problem('provider')

    try:
        with connection(AUTH_DB,True) as db:
            linked=select(db,'SELECT user_id FROM google_links WHERE google_sub=?',(subject,),True)
            if row['mode']=='link':
                actor=select(db,'''SELECT u.id,u.email FROM users u JOIN sessions s ON s.user_id=u.id
                    WHERE s.token_hash=? AND u.id=? AND u.verified=1 AND u.enabled=1 AND s.expires_at>?''',
                    (row['session_hash'],row['user_id'],stamp()),True)
                if not actor or actor['email'].lower()!=email:
                    return oauth_problem('account-mismatch')
                if linked and linked['user_id'] != actor['id']:
                    return oauth_problem('already-linked')
                db.execute('INSERT OR IGNORE INTO google_links VALUES (?,?,?,?)',
                           (subject,actor['id'],email,stamp()))
                response=RedirectResponse('/?google=linked#settings',status_code=303)
                response.delete_cookie(GOOGLE_COOKIE,path='/api/auth/google')
                return response
            if linked:
                uid=linked['user_id']
                active=select(db,'SELECT id FROM users WHERE id=? AND enabled=1 AND verified=1',(uid,),True)
                if not active:
                    return oauth_problem('disabled')
            else:
                conflict=select(db,'SELECT id FROM users WHERE email=?',(email,),True)
                if conflict:
                    # Never auto-link by matching email: require a password login first.
                    return oauth_problem('link-required')
                uid=uuid.uuid4().hex
                db.execute('INSERT INTO users(id,email,display_name,password_hash,verified,created_at) VALUES(?,?,?,?,1,?)',
                           (uid,email,name,None,stamp()))
                db.execute('INSERT INTO google_links VALUES (?,?,?,?)',(subject,uid,email,stamp()))
        init_user_db(uid)
        token,csrf=create_session(uid)
        response=RedirectResponse('/?google=welcome#overview',status_code=303)
        session_cookie(response,token)
        response.delete_cookie(GOOGLE_COOKIE,path='/api/auth/google')
        return response
    except sqlite3.IntegrityError:
        return oauth_problem('existing-account')


@app.get('/api/me')
def me(request: Request):
    user=require_user(request)
    with connection(AUTH_DB) as db:
        link=select(db,'SELECT google_sub FROM google_links WHERE user_id=?',(user['id'],),True)
    with connection(init_user_db(user['id'])) as db:
        counts={key:db.execute('SELECT COUNT(*) FROM '+key).fetchone()[0] for key in ('events','tickets','attachments','sales')}
    return {'email':user['email'],'name':user['display_name'],
            'has_google':bool(link), 'has_password':password_exists(user['id']), 'counts':counts}


def password_exists(uid):
    with connection(AUTH_DB) as db:
        row=select(db,'SELECT password_hash FROM users WHERE id=?',(uid,),True)
    return bool(row and row['password_hash'])


class Profile(BaseModel):
    name: str = Field(min_length=2,max_length=100)


@app.patch('/api/me')
def update_profile(payload: Profile, request: Request):
    user=require_user(request,True)
    with connection(AUTH_DB,True) as db:
        db.execute('UPDATE users SET display_name=? WHERE id=?',(clean(payload.name,100),user['id']))
    return {'ok':True}


class NewPassword(BaseModel):
    current_password: str = ''
    new_password: str


@app.post('/api/me/password')
def change_password(payload: NewPassword,request: Request):
    user=require_user(request,True)
    password_policy(payload.new_password)
    with connection(AUTH_DB,True) as db:
        row=select(db,'SELECT password_hash FROM users WHERE id=?',(user['id'],),True)
        if row['password_hash']:
            try:
                if not PH.verify(row['password_hash'],payload.current_password):
                    raise HTTPException(401,'Incorrect current password.')
            except (VerifyMismatchError,VerificationError):
                raise HTTPException(401,'Incorrect current password.')
        db.execute('UPDATE users SET password_hash=? WHERE id=?',(PH.hash(payload.new_password),user['id']))
        db.execute('DELETE FROM sessions WHERE user_id=? AND token_hash!=?',
                   (user['id'],digest(request.cookies[LOGIN_COOKIE])))
    return {'ok':True}


# --- Each endpoint below receives the authenticated user's *private* database. ---

class EventInput(BaseModel):
    title: str = Field(min_length=2,max_length=200)
    starts_at: str
    venue: str = Field(default='',max_length=200)
    city: str = Field(default='',max_length=120)
    country: str = Field(default='',max_length=100)
    category: str = Field(default='Concert',max_length=80)
    notes: str = Field(default='',max_length=1000)


@app.get('/api/events')
def list_events(request: Request):
    _,p=user_db(request)
    with connection(p) as db:
        return select(db,'''SELECT e.*, (SELECT COUNT(*) FROM tickets t WHERE t.event_id=e.id) AS lots,
            (SELECT COALESCE(SUM(t.quantity-t.sold_quantity),0) FROM tickets t WHERE t.event_id=e.id) AS available
            FROM events e WHERE e.archived=0 ORDER BY e.starts_at''')


@app.post('/api/events')
def add_event(payload: EventInput,request: Request):
    _,p=user_db(request,True)
    with connection(p,True) as db:
        cur=db.execute('''INSERT INTO events(title,starts_at,venue,city,country,category,notes,created_at)
            VALUES (?,?,?,?,?,?,?,?)''', (clean(payload.title,200),date_utc(payload.starts_at),payload.venue.strip(),
            payload.city.strip(),payload.country.strip(),payload.category.strip(),payload.notes.strip(),stamp()))
        log(db,'create','event',cur.lastrowid)
        return {'id':cur.lastrowid}


@app.get('/api/events/{event_id}')
def event_detail(event_id:int,request:Request):
    _,p=user_db(request)
    with connection(p) as db:
        row=select(db,'SELECT * FROM events WHERE id=?',(event_id,),True)
    if not row:
        raise HTTPException(404,'Event not found.')
    return row


@app.patch('/api/events/{event_id}')
def edit_event(event_id:int,payload:EventInput,request:Request):
    _,p=user_db(request,True)
    with connection(p,True) as db:
        row=db.execute('SELECT id FROM events WHERE id=?',(event_id,)).fetchone()
        if not row:
            raise HTTPException(404,'Event not found.')
        db.execute('''UPDATE events SET title=?,starts_at=?,venue=?,city=?,country=?,category=?,notes=?
            WHERE id=?''', (clean(payload.title,200),date_utc(payload.starts_at),payload.venue.strip(),
            payload.city.strip(),payload.country.strip(),payload.category.strip(),payload.notes.strip(),event_id))
        log(db,'edit','event',event_id)
    return {'ok':True}


class TicketInput(BaseModel):
    event_id:int
    provider:str = Field(default='',max_length=100)
    ticket_type:str = Field(default='E-Ticket',max_length=100)
    section:str = Field(default='',max_length=100)
    row_label:str = Field(default='',max_length=70)
    seats:str = Field(default='',max_length=150)
    quantity:int = Field(ge=1,le=1000)
    purchase_price:Decimal = Decimal('0')  # per-ticket cost in selected currency
    currency:str = 'EUR'
    notes:str = Field(default='',max_length=1000)


@app.get('/api/tickets')
def list_tickets(request:Request):
    _,p=user_db(request)
    with connection(p) as db:
        return select(db,'''SELECT t.*, e.title AS event_title, e.starts_at, e.city,
            (SELECT COUNT(*) FROM attachments a WHERE a.ticket_id=t.id) AS pdf_count
            FROM tickets t JOIN events e ON e.id=t.event_id
            ORDER BY t.id DESC''')


@app.post('/api/tickets')
def add_ticket(payload:TicketInput,request:Request):
    _,p=user_db(request,True)
    with connection(p,True) as db:
        if not db.execute('SELECT 1 FROM events WHERE id=? AND archived=0',(payload.event_id,)).fetchone():
            raise HTTPException(404,'Event does not exist in your account.')
        cur=db.execute('''INSERT INTO tickets(event_id,provider,ticket_type,section,row_label,seats,quantity,
            purchase_cents,currency,notes,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            (payload.event_id,payload.provider.strip(),payload.ticket_type.strip(),payload.section.strip(),
            payload.row_label.strip(),payload.seats.strip(),payload.quantity,cents(payload.purchase_price),
            currency(payload.currency),payload.notes.strip(),stamp()))
        log(db,'create','ticket',cur.lastrowid)
        return {'id':cur.lastrowid}


@app.post('/api/tickets/{ticket_id}/pdf')
async def add_pdf(ticket_id:int,request:Request,file:UploadFile=File(...)):
    user,p=user_db(request,True)
    if file.content_type not in ('application/pdf','application/octet-stream'):
        raise HTTPException(415,'Upload a PDF document.')
    raw=await file.read(20*1024*1024+1)
    if len(raw)>20*1024*1024:
        raise HTTPException(413,'PDF file exceeds the 20 MB limit.')
    if not raw.startswith(b'%PDF-'):
        raise HTTPException(415,'This file is not a PDF document.')
    filename=clean(Path((file.filename or 'ticket.pdf').replace('\\','/')).name,180)
    checksum=hashlib.sha256(raw).hexdigest()
    file_key=secrets.token_hex(20)+'.encrypted'
    vault=storage_dir(user['id'])/'vault'
    with connection(p,True) as db:
        if not db.execute('SELECT 1 FROM tickets WHERE id=?',(ticket_id,)).fetchone():
            raise HTTPException(404,'Ticket not found.')
        if db.execute('SELECT 1 FROM attachments WHERE ticket_id=? AND sha256=?',(ticket_id,checksum)).fetchone():
            raise HTTPException(409,'This PDF is already attached to the ticket.')
        used=db.execute('SELECT COUNT(*),COALESCE(SUM(size),0) FROM attachments').fetchone()
        if used[0]>=300 or used[1]+len(raw)>1024*1024*1024:
            raise HTTPException(413,'Your personal PDF vault has reached its safety quota.')
        encrypted=personal_key(user['id']).encrypt(raw)
        target=vault/file_key
        try:
            with target.open('xb') as handle:
                handle.write(encrypted)
            cur=db.execute('''INSERT INTO attachments(ticket_id,filename,path,sha256,size,created_at)
                VALUES(?,?,?,?,?,?)''',(ticket_id,filename,file_key,checksum,len(raw),stamp()))
            log(db,'attach-pdf','ticket',ticket_id)
        except Exception:
            target.unlink(missing_ok=True)
            raise
    return {'id':cur.lastrowid,'filename':filename,'size':len(raw)}


@app.get('/api/tickets/{ticket_id}/pdfs')
def list_pdfs(ticket_id:int,request:Request):
    _,p=user_db(request)
    with connection(p) as db:
        if not db.execute('SELECT 1 FROM tickets WHERE id=?',(ticket_id,)).fetchone():
            raise HTTPException(404,'Ticket not found.')
        return select(db,'SELECT id,filename,size,created_at FROM attachments WHERE ticket_id=? ORDER BY id DESC',(ticket_id,))


@app.get('/api/tickets/{ticket_id}/pdfs/{attachment_id}')
def download_pdf(ticket_id:int,attachment_id:int,request:Request):
    user,p=user_db(request)
    with connection(p) as db:
        a=select(db,'SELECT * FROM attachments WHERE ticket_id=? AND id=?',(ticket_id,attachment_id),True)
    if not a:
        raise HTTPException(404,'PDF not found in your account.')
    path=storage_dir(user['id'])/'vault'/a['path']
    if not path.is_file():
        raise HTTPException(404,'Stored document is missing.')
    try:
        blob=personal_key(user['id']).decrypt(path.read_bytes())
    except Exception:
        raise HTTPException(500,'Cannot decrypt the PDF; check your backup encryption key.')
    fname=a['filename'].replace('"','').replace('\r','').replace('\n','')
    return Response(content=blob,media_type='application/pdf',headers={
        'Content-Disposition':'attachment; filename="'+fname+'"',
        'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff'})


class ListingInput(BaseModel):
    ticket_id:int
    marketplace:str = Field(default='viagogo',max_length=80)
    external_id:str = Field(default='',max_length=150)
    price:Decimal
    currency:str = 'EUR'
    status:Literal['draft','ready','listed','paused','sold','cancelled'] = 'draft'
    notes:str = Field(default='',max_length=1000)


@app.get('/api/listings')
def list_listings(request:Request):
    _,p=user_db(request)
    with connection(p) as db:
        return select(db,'''SELECT l.*,t.section,t.seats,t.quantity,t.sold_quantity,
          e.title AS event_title FROM listings l
          JOIN tickets t ON t.id=l.ticket_id JOIN events e ON e.id=t.event_id
          ORDER BY l.id DESC''')


@app.post('/api/listings')
def add_listing(payload:ListingInput,request:Request):
    _,p=user_db(request,True)
    with connection(p,True) as db:
        ticket=select(db,'SELECT * FROM tickets WHERE id=?',(payload.ticket_id,),True)
        if not ticket:
            raise HTTPException(404,'Ticket not found.')
        if ticket['quantity']<=ticket['sold_quantity']:
            raise HTTPException(409,'No available tickets remain.')
        if payload.status in ('ready','listed') and db.execute('''SELECT 1 FROM listings WHERE ticket_id=?
            AND status IN ('ready','listed')''',(payload.ticket_id,)).fetchone():
            raise HTTPException(409,'This ticket already has an active listing.')
        cur=db.execute('''INSERT INTO listings(ticket_id,marketplace,external_id,price_cents,currency,status,notes,created_at)
            VALUES (?,?,?,?,?,?,?,?)''', (payload.ticket_id,clean(payload.marketplace,80),
            payload.external_id.strip(),cents(payload.price),currency(payload.currency),payload.status,
            payload.notes.strip(),stamp()))
        log(db,'create','listing',cur.lastrowid)
        return {'id':cur.lastrowid,'notice':'Local listing only. No automatic marketplace publication.'}


@app.patch('/api/listings/{listing_id}')
def edit_listing(listing_id:int,payload:ListingInput,request:Request):
    _,p=user_db(request,True)
    with connection(p,True) as db:
        existing=select(db,'SELECT * FROM listings WHERE id=?',(listing_id,),True)
        if not existing:
            raise HTTPException(404,'Listing not found.')
        if existing['ticket_id']!=payload.ticket_id:
            raise HTTPException(400,'You cannot change the ticket for an existing listing.')
        if payload.status in ('listed','ready'):
            if db.execute('''SELECT 1 FROM listings WHERE ticket_id=? AND id!=?
                AND status IN ('ready','listed')''',(payload.ticket_id,listing_id)).fetchone():
                raise HTTPException(409,'Another listing for this ticket is active.')
        db.execute('''UPDATE listings SET marketplace=?,external_id=?,price_cents=?,currency=?,status=?,notes=? WHERE id=?''',
                   (clean(payload.marketplace,80),payload.external_id.strip(),cents(payload.price),
                    currency(payload.currency),payload.status,payload.notes.strip(),listing_id))
        log(db,'update','listing',listing_id)
    return {'ok':True}


class SaleInput(BaseModel):
    ticket_id:int
    listing_id:int|None=None
    quantity:int=Field(ge=1,le=1000)
    revenue:Decimal
    fees:Decimal=Decimal('0')
    currency:str='EUR'
    sold_at:str
    channel:str=Field(default='Direct',max_length=100)
    reference:str=Field(default='',max_length=200)


@app.get('/api/sales')
def list_sales(request:Request):
    _,p=user_db(request)
    with connection(p) as db:
        return select(db,'''SELECT s.*,e.title AS event_title,t.section,t.purchase_cents,
            t.currency AS cost_currency FROM sales s
            JOIN tickets t ON t.id=s.ticket_id JOIN events e ON e.id=t.event_id
            ORDER BY s.sold_at DESC''')


@app.post('/api/sales')
def add_sale(payload:SaleInput,request:Request):
    _,p=user_db(request,True)
    with connection(p,True) as db:
        t=select(db,'SELECT * FROM tickets WHERE id=?',(payload.ticket_id,),True)
        if not t:
            raise HTTPException(404,'Ticket does not exist in your account.')
        if payload.quantity>t['quantity']-t['sold_quantity']:
            raise HTTPException(409,'Not enough unsold tickets available.')
        if payload.listing_id is not None:
            listing=select(db,'SELECT ticket_id FROM listings WHERE id=?',(payload.listing_id,),True)
            if not listing or listing['ticket_id']!=payload.ticket_id:
                raise HTTPException(422,'Listing does not belong to the selected ticket.')
        price=cents(payload.revenue);fees=cents(payload.fees)
        if fees>price:
            raise HTTPException(422,'Fees cannot exceed sale revenue.')
        cur=db.execute('''INSERT INTO sales(ticket_id,listing_id,quantity,revenue_cents,fee_cents,
          currency,sold_at,channel,reference,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)''',
          (payload.ticket_id,payload.listing_id,payload.quantity,price,fees,currency(payload.currency),
           date_utc(payload.sold_at),clean(payload.channel,100),payload.reference.strip(),stamp()))
        db.execute('UPDATE tickets SET sold_quantity=sold_quantity+? WHERE id=?',(payload.quantity,payload.ticket_id))
        log(db,'create','sale',cur.lastrowid)
        return {'id':cur.lastrowid}


class ExpenseInput(BaseModel):
    event_id:int|None=None
    title:str=Field(min_length=2,max_length=150)
    amount:Decimal
    currency:str='EUR'


@app.get('/api/expenses')
def list_expenses(request:Request):
    _,p=user_db(request)
    with connection(p) as db:
        return select(db,'''SELECT x.*,e.title AS event_title FROM expenses x
          LEFT JOIN events e ON e.id=x.event_id ORDER BY x.id DESC''')


@app.post('/api/expenses')
def add_expense(payload:ExpenseInput,request:Request):
    _,p=user_db(request,True)
    with connection(p,True) as db:
        if payload.event_id is not None and not db.execute('SELECT 1 FROM events WHERE id=?',(payload.event_id,)).fetchone():
            raise HTTPException(404,'Event does not exist in your account.')
        cur=db.execute('''INSERT INTO expenses(event_id,title,amount_cents,currency,created_at) VALUES (?,?,?,?,?)''',
                       (payload.event_id,clean(payload.title,150),cents(payload.amount),currency(payload.currency),stamp()))
        log(db,'create','expense',cur.lastrowid)
        return {'id':cur.lastrowid}


def compute_recaps(db):
    events=select(db,'SELECT id,title,starts_at,city,venue FROM events WHERE archived=0 ORDER BY starts_at DESC')
    result=[]
    for e in events:
        sold=select(db,'''SELECT s.quantity,s.revenue_cents,s.fee_cents,s.currency,
            t.purchase_cents,t.currency AS purchase_currency FROM sales s
            JOIN tickets t ON t.id=s.ticket_id WHERE t.event_id=?''',(e['id'],))
        # Only EUR is aggregated, to avoid silently conflating currencies.
        eur_sales=[s for s in sold if s['currency']=='EUR' and s['purchase_currency']=='EUR']
        revenue=sum(s['revenue_cents'] for s in eur_sales)
        fees=sum(s['fee_cents'] for s in eur_sales)
        cost=sum(s['quantity']*s['purchase_cents'] for s in eur_sales)
        expenses=select(db,'SELECT amount_cents,currency FROM expenses WHERE event_id=?',(e['id'],))
        expense_cents=sum(x['amount_cents'] for x in expenses if x['currency']=='EUR')
        sold_count=sum(s['quantity'] for s in sold)
        available=db.execute('SELECT COALESCE(SUM(quantity-sold_quantity),0) FROM tickets WHERE event_id=?',(e['id'],)).fetchone()[0]
        profit=revenue-fees-cost-expense_cents
        investment=cost+expense_cents
        result.append({**e,'sold':sold_count,'available':available,'revenue_cents':revenue,
                       'fee_cents':fees,'sold_cost_cents':cost,'expenses_cents':expense_cents,
                       'profit_cents':profit,'roi_percent':round(profit*100/investment,2) if investment else None,
                       'has_non_eur':any(s['currency']!='EUR' or s['purchase_currency']!='EUR' for s in sold)
                           or any(x['currency']!='EUR' for x in expenses)})
    return result


@app.get('/api/recaps')
def recaps(request:Request):
    _,p=user_db(request)
    with connection(p) as db:
        return compute_recaps(db)


@app.get('/api/dashboard')
def dashboard(request:Request):
    _,p=user_db(request)
    with connection(p) as db:
        counts={table:db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
                for table in ('events','tickets','attachments','listings','sales')}
        available=db.execute('SELECT COALESCE(SUM(quantity-sold_quantity),0) FROM tickets').fetchone()[0]
        sold=db.execute('SELECT COALESCE(SUM(quantity),0) FROM sales').fetchone()[0]
        recaps=compute_recaps(db)
        recent=select(db,'''SELECT s.id,s.sold_at,s.revenue_cents,s.currency,s.quantity,e.title AS event_title
          FROM sales s JOIN tickets t ON t.id=s.ticket_id JOIN events e ON e.id=t.event_id
          ORDER BY s.sold_at DESC LIMIT 6''')
        series=select(db,'''SELECT substr(sold_at,1,10) AS day, SUM(revenue_cents) AS revenue_cents,
          SUM(quantity) AS quantity FROM sales WHERE currency='EUR'
          GROUP BY day ORDER BY day DESC LIMIT 14''')
        series.reverse()
        return {**counts,'available':available,'sold':sold,
                'revenue_cents':sum(x['revenue_cents'] for x in recaps),
                'profit_cents':sum(x['profit_cents'] for x in recaps),
                'recaps':sorted(recaps,key=lambda e:e['profit_cents'],reverse=True)[:6],
                'recent_sales':recent,'revenue_trend':series}


@app.get('/api/audit')
def audit(request:Request):
    _,p=user_db(request)
    with connection(p) as db:
        return select(db,'SELECT * FROM audit ORDER BY id DESC LIMIT 50')


@app.get('/api/export/{table_name}.csv')
def export_csv(table_name:Literal['events','tickets','listings','sales','expenses'],request:Request):
    _,p=user_db(request)
    with connection(p) as db:
        rows=select(db,'SELECT * FROM '+table_name+' ORDER BY id DESC')
        columns=[x['name'] for x in db.execute('PRAGMA table_info('+table_name+')').fetchall()]
    output=io.StringIO()
    writer=csv.DictWriter(output,fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({k:("'"+str(v) if str(v).startswith(('=','+','-','@')) else v) for k,v in row.items()})
    return Response(output.getvalue(),media_type='text/csv; charset=utf-8',headers={
        'Content-Disposition':'attachment; filename="'+table_name+'.csv"'})


# Ceyrl V6: optional, read-only per-user intelligence. Existing API contracts stay intact.
from ceyrl_v6 import install_v6_routes

install_v6_routes(
    app,
    user_db=user_db,
    connection=connection,
    select=select,
)
