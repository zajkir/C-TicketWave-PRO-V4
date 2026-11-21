"""C TicketWave PRO — persistent, team-based ticket inventory service.

A single-workspace application for a trusted ticketing team. All inventory and
files are local to the configured server; users have individual accounts.
"""
from __future__ import annotations

import asyncio
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv
from fastapi import FastAPI, Request, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field, field_validator

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
DATA = Path(os.environ.get('CTW_DATA_DIR', str(ROOT / 'data'))).expanduser().resolve()
DATA.mkdir(parents=True, exist_ok=True)
VAULT = DATA / 'vault'
VAULT.mkdir(exist_ok=True)
DBFILE = DATA / 'ticketwave.sqlite3'
MAX_FILE = 20 * 1024 * 1024
DB_LOCK = threading.RLock()
ROLES = {'viewer': 0, 'operator': 1, 'manager': 2, 'admin': 3}
HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
SESSION_TTL = 60 * 60 * 12
COOKIE = 'ctw_session'
SECURE_COOKIE = os.environ.get('CTW_SECURE_COOKIES', '0') == '1'
AUTH_FAILURES: dict[str, list[float]] = {}


def secret_file(filename, generator):
    path = DATA / filename
    try:
        with open(path, 'xb') as stream:
            os.chmod(path, 0o600)
            stream.write(generator())
    except FileExistsError:
        pass
    return path.read_bytes().strip()


CIPHER = Fernet(secret_file('.encryption_key', Fernet.generate_key))


def utcnow():
    return datetime.now(timezone.utc)


def timestamp():
    return utcnow().isoformat()


def parse_date(value):
    try:
        d = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if d.tzinfo is None:
            raise ValueError('timezone required')
        return d.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        raise HTTPException(422, 'Enter a date including the timezone offset (e.g. 2027-06-01T19:00:00+02:00).')


def amount_cents(value):
    try:
        num = Decimal(str(value))
        if not num.is_finite() or num < 0 or num > 100000000:
            raise ValueError('out of range')
        cents = (num * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        return int(cents)
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(422, 'Enter a valid non-negative amount.')


def fee_basis_points(value):
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n < 0 or n > 50:
            raise ValueError()
        return int((n * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        raise HTTPException(422, 'Commission must be between 0 and 50%.')


def clean(value, max_len=200, required=True):
    result = (value or '').strip()
    if (required and not result) or len(result) > max_len:
        raise HTTPException(422, 'A required field is empty or too long.')
    return result


def currency(value):
    val = str(value or 'EUR').upper().strip()
    if val not in {'EUR', 'USD', 'GBP', 'CZK', 'PLN', 'CHF'}:
        raise HTTPException(422, 'Unsupported currency code.')
    return val


@contextmanager
def db(write=False):
    # A single-application DB for a small team. WAL and explicit IMMEDIATE
    # transactions serialize stock changes even across uvicorn processes.
    with DB_LOCK:
        connection = sqlite3.connect(DBFILE, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA busy_timeout=30000')
        try:
            if write:
                connection.execute('BEGIN IMMEDIATE')
            else:
                connection.execute('BEGIN')
            yield connection
            connection.execute('COMMIT')
        except Exception:
            if connection.in_transaction:
                connection.execute('ROLLBACK')
            raise
        finally:
            connection.close()


def fetch(query, args=(), first=False):
    with db() as connection:
        result = connection.execute(query, args)
        if first:
            x = result.fetchone()
            return dict(x) if x else None
        return [dict(x) for x in result.fetchall()]


def log(conn, user_id, action, entity, entity_id, detail=''):
    conn.execute('INSERT INTO audit(user_id,action,entity,entity_id,detail,created_at) VALUES (?,?,?,?,?,?)',
                 (user_id, action, entity, entity_id, str(detail)[:900], timestamp()))


def init_db():
    with sqlite3.connect(DBFILE, timeout=30) as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA foreign_keys=ON')
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            name TEXT NOT NULL, password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','manager','operator','viewer')),
            enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, last_login TEXT
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
            csrf TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
        CREATE TABLE IF NOT EXISTS invites (
            id INTEGER PRIMARY KEY, email TEXT NOT NULL, role TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE, expires_at TEXT NOT NULL,
            used_at TEXT, created_at TEXT NOT NULL, created_by INTEGER REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS resets (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
            token_hash TEXT NOT NULL UNIQUE, expires_at TEXT NOT NULL,
            used_at TEXT, created_at TEXT NOT NULL, created_by INTEGER REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY, title TEXT NOT NULL, starts_at TEXT NOT NULL,
            venue TEXT NOT NULL, city TEXT NOT NULL, country TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'Concert', external_source TEXT,
            external_id TEXT, archived INTEGER NOT NULL DEFAULT 0,
            created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_event_external ON events(external_source,external_id)
            WHERE external_source IS NOT NULL AND external_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_event_date ON events(starts_at);
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES events(id),
            source TEXT NOT NULL DEFAULT '', type TEXT NOT NULL DEFAULT 'E-Ticket',
            section TEXT NOT NULL DEFAULT '', row_label TEXT NOT NULL DEFAULT '',
            seats TEXT NOT NULL DEFAULT '', quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 100),
            sold_quantity INTEGER NOT NULL DEFAULT 0 CHECK(sold_quantity >= 0 AND sold_quantity <= quantity),
            cost_cents INTEGER NOT NULL DEFAULT 0, face_cents INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'EUR', status TEXT NOT NULL DEFAULT 'available',
            notes TEXT NOT NULL DEFAULT '', original_filename TEXT, stored_filename TEXT,
            file_hash TEXT, created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_ticket_pdf_event ON tickets(event_id,file_hash) WHERE file_hash IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_ticket_event ON tickets(event_id);
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id),
            marketplace TEXT NOT NULL DEFAULT 'viagogo', status TEXT NOT NULL DEFAULT 'draft',
            price_cents INTEGER NOT NULL, commission_bp INTEGER NOT NULL DEFAULT 1000,
            currency TEXT NOT NULL DEFAULT 'EUR', external_id TEXT, notes TEXT NOT NULL DEFAULT '',
            created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_active_listing ON listings(ticket_id)
            WHERE status IN ('draft','ready','listed','review');
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id),
            listing_id INTEGER REFERENCES listings(id), quantity INTEGER NOT NULL,
            amount_cents INTEGER NOT NULL, fee_cents INTEGER NOT NULL DEFAULT 0,
            channel TEXT NOT NULL, reference TEXT NOT NULL DEFAULT '',
            sold_at TEXT NOT NULL, currency TEXT NOT NULL DEFAULT 'EUR',
            created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY, event_id INTEGER REFERENCES events(id),
            label TEXT NOT NULL, amount_cents INTEGER NOT NULL, currency TEXT NOT NULL DEFAULT 'EUR',
            incurred_at TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
            created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY, keyword TEXT NOT NULL, country TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1, last_synced TEXT, last_error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, created_by INTEGER REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS integration_secrets (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider TEXT NOT NULL, value_enc BLOB NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY(user_id, provider)
        );
        CREATE TABLE IF NOT EXISTS oauth_pending (
            state_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            redirect_uri TEXT NOT NULL, expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id),
            action TEXT NOT NULL, entity TEXT NOT NULL, entity_id INTEGER,
            detail TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        ''')


init_db()


async def sync_watchlist_background():
    # Runs when the API service is live. Not a guaranteed scheduler; documented
    # limitation when the process is asleep/stopped.
    while True:
        await asyncio.sleep(6 * 60 * 60)
        if os.environ.get('TICKETMASTER_API_KEY') or fetch("SELECT 1 AS yes FROM integration_secrets WHERE provider='ticketmaster' LIMIT 1", first=True):
            try:
                await sync_watchlist()
            except Exception as e:
                print('watchlist sync failed:', str(e)[:200])


@asynccontextmanager
async def lifespan(_app):
    # The legacy Ticketmaster watchlist is hidden in the V4 interface.
    # Do not run scheduled imports without an explicit administrator opt-in.
    task = (asyncio.create_task(sync_watchlist_background())
            if os.environ.get('CTW_ENABLE_LEGACY_WATCHLIST') == '1' else None)
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(title='C TicketWave PRO', version='4.0.0', docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')


@app.middleware('http')
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    response.headers['Cache-Control'] = 'no-store'
    if SECURE_COOKIE:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


def enforce_origin(request):
    origin = request.headers.get('origin')
    if not origin:
        return
    allowed = {x.strip().rstrip('/') for x in os.environ.get('CTW_ALLOWED_ORIGINS', '').split(',') if x.strip()}
    current = str(request.base_url).rstrip('/')
    if origin != current and origin not in allowed:
        raise HTTPException(403, 'Invalid request origin.')


def rate_guard(key):
    current = time.monotonic()
    hits = [x for x in AUTH_FAILURES.get(key, []) if current - x < 600]
    if len(hits) >= 8:
        raise HTTPException(429, 'Too many attempts. Retry after 10 minutes.')
    AUTH_FAILURES[key] = hits


def rate_fail(key):
    AUTH_FAILURES.setdefault(key, []).append(time.monotonic())


def issue_session(request, user_id):
    token = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    with db(write=True) as conn:
        conn.execute('DELETE FROM sessions WHERE expires_at < ?', (timestamp(),))
        conn.execute('INSERT INTO sessions(id_hash,user_id,csrf,expires_at,created_at) VALUES(?,?,?,?,?)',
                     (hashlib.sha256(token.encode()).hexdigest(), user_id, csrf,
                      (utcnow() + timedelta(seconds=SESSION_TTL)).isoformat(), timestamp()))
    return token, csrf


def set_session_cookie(response, token):
    response.set_cookie(COOKIE, token, httponly=True, secure=SECURE_COOKIE,
                        samesite='strict', max_age=SESSION_TTL, path='/')


def auth(request: Request, role='viewer', mutate=False):
    if mutate:
        enforce_origin(request)
    token = request.cookies.get(COOKIE, '')
    if not token or len(token) > 200:
        raise HTTPException(401, 'Please sign in to continue.')
    user = fetch('''SELECT u.id,u.email,u.name,u.role,u.enabled,s.csrf
                    FROM sessions s JOIN users u ON u.id=s.user_id
                    WHERE s.id_hash=? AND s.expires_at > ?''',
                 (hashlib.sha256(token.encode()).hexdigest(), timestamp()), first=True)
    if not user or not user['enabled']:
        raise HTTPException(401, 'Your session has expired. Please sign in again.')
    if ROLES[user['role']] < ROLES[role]:
        raise HTTPException(403, 'Your role does not permit this action.')
    if mutate:
        csrf = request.headers.get('x-csrf-token', '')
        if not csrf or not hmac.compare_digest(csrf, user['csrf']):
            raise HTTPException(403, 'Invalid CSRF token. Please reload and retry.')
    return user


def public_user(user):
    return {k: user[k] for k in ('id', 'email', 'name', 'role')}


class Credentials(BaseModel):
    email: str = Field(min_length=5, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class Bootstrap(Credentials):
    name: str = Field(min_length=2, max_length=100)
    setup_code: str = ''


class AcceptInvite(Bootstrap):
    token: str


class InviteInput(BaseModel):
    email: str = Field(min_length=5, max_length=200)
    role: Literal['admin', 'manager', 'operator', 'viewer'] = 'operator'


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


def validate_email(email):
    email = clean(email, 200).lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise HTTPException(422, 'Enter a valid email address.')
    return email


def validate_password(password):
    if len(password) < 12 or len(password) > 200:
        raise HTTPException(422, 'Password must have at least 12 characters.')
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise HTTPException(422, 'Password must contain letters and numbers.')


@app.get('/')
def main():
    return FileResponse(ROOT / 'static' / 'index.html', media_type='text/html')


@app.get('/api/auth/state')
def auth_state(request: Request):
    setup = fetch('SELECT count(*) AS n FROM users', first=True)['n'] == 0
    try:
        user = auth(request)
        return {'setup_required': False, 'authenticated': True, 'user': public_user(user),
                'csrf': user['csrf'], 'ticketmaster_connected': bool(os.environ.get('TICKETMASTER_API_KEY'))}
    except HTTPException:
        return {'setup_required': setup, 'authenticated': False, 'user': None,
                'ticketmaster_connected': bool(os.environ.get('TICKETMASTER_API_KEY'))}


@app.post('/api/auth/bootstrap')
def bootstrap(payload: Bootstrap, request: Request):
    enforce_origin(request)
    code = os.environ.get('CTW_BOOTSTRAP_CODE', '')
    caller = request.client.host if request.client else ''
    if code and not hmac.compare_digest(code, payload.setup_code):
        raise HTTPException(403, 'Invalid initial setup code.')
    if not code and not (os.environ.get('CTW_ALLOW_LOCAL_SETUP') == '1' and caller in ('127.0.0.1', '::1', 'localhost', 'testclient')):
        raise HTTPException(403, 'Remote setup requires CTW_BOOTSTRAP_CODE on the server.')
    email = validate_email(payload.email)
    validate_password(payload.password)
    with db(write=True) as conn:
        if conn.execute('SELECT count(*) FROM users').fetchone()[0]:
            raise HTTPException(409, 'This workspace already has an administrator.')
        cur = conn.execute('''INSERT INTO users(email,name,password_hash,role,created_at)
            VALUES(?,?,?,?,?)''', (email, clean(payload.name,100), HASHER.hash(payload.password), 'admin', timestamp()))
        user_id = cur.lastrowid
        log(conn, user_id, 'workspace.created', 'user', user_id, 'First administrator')
    session, csrf = issue_session(request, user_id)
    result = Response(content=json.dumps({'ok': True, 'csrf': csrf}), media_type='application/json')
    set_session_cookie(result, session)
    return result


@app.post('/api/auth/login')
def login(payload: Credentials, request: Request):
    enforce_origin(request)
    email = validate_email(payload.email)
    key = (request.client.host if request.client else 'unknown') + ':' + email
    rate_guard(key)
    user = fetch('SELECT * FROM users WHERE email=?', (email,), first=True)
    valid = False
    if user and user['enabled']:
        try:
            valid = HASHER.verify(user['password_hash'], payload.password)
        except (VerifyMismatchError, VerificationError):
            pass
    if not valid:
        rate_fail(key)
        raise HTTPException(401, 'Incorrect email or password.')
    AUTH_FAILURES.pop(key, None)
    session, csrf = issue_session(request, user['id'])
    with db(write=True) as conn:
        conn.execute('UPDATE users SET last_login=? WHERE id=?', (timestamp(), user['id']))
        log(conn, user['id'], 'auth.login', 'user', user['id'])
    result = Response(content=json.dumps({'ok': True, 'csrf': csrf}), media_type='application/json')
    set_session_cookie(result, session)
    return result


@app.post('/api/auth/logout')
def logout(request: Request):
    user = auth(request, mutate=True)
    token_hash = hashlib.sha256(request.cookies[COOKIE].encode()).hexdigest()
    with db(write=True) as conn:
        conn.execute('DELETE FROM sessions WHERE id_hash=?', (token_hash,))
        log(conn, user['id'], 'auth.logout', 'user', user['id'])
    response = Response(content='{"ok":true}', media_type='application/json')
    response.delete_cookie(COOKIE, path='/')
    return response


@app.post('/api/auth/password')
def change_password(payload: PasswordChange, request: Request):
    user = auth(request, mutate=True)
    validate_password(payload.new_password)
    row = fetch('SELECT password_hash FROM users WHERE id=?', (user['id'],), first=True)
    try:
        if not HASHER.verify(row['password_hash'], payload.current_password):
            raise HTTPException(401, 'Incorrect current password.')
    except (VerifyMismatchError, VerificationError):
        raise HTTPException(401, 'Incorrect current password.')
    with db(write=True) as conn:
        conn.execute('UPDATE users SET password_hash=? WHERE id=?',
                     (HASHER.hash(payload.new_password), user['id']))
        conn.execute('DELETE FROM sessions WHERE user_id=? AND id_hash!=?',
                     (user['id'], hashlib.sha256(request.cookies[COOKIE].encode()).hexdigest()))
        log(conn, user['id'], 'auth.password_change', 'user', user['id'])
    return {'ok': True}


@app.get('/api/team')
def list_team(request: Request):
    auth(request, 'manager')
    return fetch('SELECT id,email,name,role,enabled,created_at,last_login FROM users ORDER BY id')


@app.get('/api/team/invites')
def list_invites(request: Request):
    auth(request, 'admin')
    return fetch('SELECT id,email,role,expires_at,used_at,created_at FROM invites ORDER BY id DESC LIMIT 100')


@app.post('/api/team/invites')
def create_invite(payload: InviteInput, request: Request):
    actor = auth(request, 'admin', mutate=True)
    email = validate_email(payload.email)
    if fetch('SELECT id FROM users WHERE email=?', (email,), first=True):
        raise HTTPException(409, 'This email already belongs to a team member.')
    token = secrets.token_urlsafe(32)
    with db(write=True) as conn:
        cur = conn.execute('''INSERT INTO invites(email,role,token_hash,expires_at,created_at,created_by)
            VALUES (?,?,?,?,?,?)''', (email, payload.role, hashlib.sha256(token.encode()).hexdigest(),
            (utcnow()+timedelta(days=2)).isoformat(), timestamp(), actor['id']))
        log(conn, actor['id'], 'team.invite_created', 'invite', cur.lastrowid, email)
    # Never persisted or logged in plaintext. Share with the intended team member securely.
    return {'token': token, 'email': email, 'role': payload.role, 'expires_in_hours': 48}


class ResetPasswordInput(BaseModel):
    token: str
    email: str
    new_password: str


@app.post('/api/team/{member_id}/password-reset')
def issue_password_reset(member_id: int, request: Request):
    actor = auth(request, 'admin', mutate=True)
    member = fetch('SELECT id,email,enabled FROM users WHERE id=?', (member_id,), first=True)
    if not member or not member['enabled']:
        raise HTTPException(404, 'Active team member not found.')
    token = secrets.token_urlsafe(32)
    with db(write=True) as conn:
        conn.execute('''INSERT INTO resets(user_id,token_hash,expires_at,created_at,created_by)
            VALUES (?,?,?,?,?)''', (member_id, hashlib.sha256(token.encode()).hexdigest(),
            (utcnow()+timedelta(minutes=30)).isoformat(), timestamp(), actor['id']))
        log(conn,actor['id'],'auth.reset_issued','user',member_id)
    # Share the one-time link via a trusted communication channel.
    return {'token': token, 'email': member['email'], 'expires_in_minutes': 30}


@app.post('/api/auth/reset-password')
def reset_password(payload: ResetPasswordInput, request: Request):
    enforce_origin(request)
    validate_password(payload.new_password)
    email = validate_email(payload.email)
    digest = hashlib.sha256(payload.token.encode()).hexdigest()
    with db(write=True) as conn:
        row = conn.execute('''SELECT r.id,r.user_id FROM resets r
            JOIN users u ON u.id=r.user_id
            WHERE r.token_hash=? AND r.expires_at>? AND r.used_at IS NULL
                AND u.email=? AND u.enabled=1''', (digest,timestamp(),email)).fetchone()
        if not row:
            raise HTTPException(404, 'Password reset link is invalid or expired.')
        conn.execute('UPDATE users SET password_hash=? WHERE id=?',
                     (HASHER.hash(payload.new_password),row['user_id']))
        conn.execute('UPDATE resets SET used_at=? WHERE id=?',(timestamp(),row['id']))
        conn.execute('DELETE FROM sessions WHERE user_id=?',(row['user_id'],))
        log(conn,row['user_id'],'auth.password_reset','user',row['user_id'])
    return {'ok':True}


@app.post('/api/auth/invite')
def accept_invite(payload: AcceptInvite, request: Request):
    enforce_origin(request)
    email = validate_email(payload.email)
    validate_password(payload.password)
    with db(write=True) as conn:
        inv = conn.execute('''SELECT * FROM invites WHERE token_hash=? AND used_at IS NULL
            AND expires_at > ?''', (hashlib.sha256(payload.token.encode()).hexdigest(), timestamp())).fetchone()
        if not inv or inv['email'].lower() != email:
            raise HTTPException(404, 'Invite is invalid, expired or for a different email.')
        try:
            cur = conn.execute('''INSERT INTO users(email,name,password_hash,role,created_at)
                VALUES(?,?,?,?,?)''', (email, clean(payload.name,100), HASHER.hash(payload.password), inv['role'], timestamp()))
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'Account already exists.')
        conn.execute('UPDATE invites SET used_at=? WHERE id=?', (timestamp(), inv['id']))
        log(conn, cur.lastrowid, 'team.invite_accepted', 'user', cur.lastrowid)
        uid = cur.lastrowid
    session, csrf = issue_session(request, uid)
    response = Response(content=json.dumps({'ok': True, 'csrf': csrf}), media_type='application/json')
    set_session_cookie(response, session)
    return response


class MemberPatch(BaseModel):
    role: Literal['admin','manager','operator','viewer'] | None = None
    enabled: bool | None = None


@app.patch('/api/team/{member_id}')
def update_member(member_id: int, payload: MemberPatch, request: Request):
    actor = auth(request, 'admin', mutate=True)
    if actor['id'] == member_id:
        raise HTTPException(409, 'You cannot alter your own access. Ask another administrator.')
    with db(write=True) as conn:
        member = conn.execute('SELECT * FROM users WHERE id=?', (member_id,)).fetchone()
        if not member:
            raise HTTPException(404, 'Member not found.')
        role = payload.role or member['role']
        enabled = member['enabled'] if payload.enabled is None else int(payload.enabled)
        if member['role'] == 'admin' and (role != 'admin' or not enabled):
            if conn.execute("SELECT count(*) FROM users WHERE role='admin' AND enabled=1").fetchone()[0] < 2:
                raise HTTPException(409, 'You must retain at least one active administrator.')
        conn.execute('UPDATE users SET role=?,enabled=? WHERE id=?', (role,enabled,member_id))
        if not enabled:
            conn.execute('DELETE FROM sessions WHERE user_id=?', (member_id,))
        log(conn, actor['id'], 'team.member_updated', 'user', member_id,
            json.dumps({'role': role, 'enabled': bool(enabled)}))
    return {'ok': True}


class EventInput(BaseModel):
    title: str = Field(min_length=2,max_length=180)
    starts_at: str
    venue: str = Field(min_length=2,max_length=180)
    city: str = Field(min_length=2,max_length=100)
    country: str = Field(min_length=2,max_length=60)
    category: str = 'Concert'


@app.get('/api/events')
def list_events(request: Request, q: str='', include_archived: bool=False):
    auth(request)
    return fetch('''SELECT e.*, COUNT(DISTINCT t.id) AS lots, COALESCE(SUM(t.quantity-t.sold_quantity),0) AS remaining
        FROM events e LEFT JOIN tickets t ON t.event_id=e.id
        WHERE (?=1 OR e.archived=0) AND (e.title LIKE ? OR e.city LIKE ? OR e.venue LIKE ?)
        GROUP BY e.id ORDER BY e.starts_at DESC LIMIT 500''',
        (int(include_archived),*(('%'+q[:100]+'%',)*3)))


@app.post('/api/events')
def create_event(payload: EventInput, request: Request):
    actor = auth(request, 'operator', mutate=True)
    with db(write=True) as conn:
        cur = conn.execute('''INSERT INTO events(title,starts_at,venue,city,country,category,created_by,created_at)
            VALUES (?,?,?,?,?,?,?,?)''', (clean(payload.title,180),parse_date(payload.starts_at),
            clean(payload.venue,180),clean(payload.city,100),clean(payload.country,60),
            clean(payload.category,40),actor['id'],timestamp()))
        log(conn,actor['id'],'event.created','event',cur.lastrowid,payload.title)
        return {'id':cur.lastrowid}


@app.patch('/api/events/{event_id}/archive')
def archive_event(event_id:int,request:Request):
    actor=auth(request,'manager',mutate=True)
    with db(write=True) as conn:
        cur=conn.execute('UPDATE events SET archived=1 WHERE id=?',(event_id,))
        if not cur.rowcount:raise HTTPException(404,'Event not found.')
        log(conn,actor['id'],'event.archived','event',event_id)
    return {'ok':True}


@app.get('/api/tickets')
def list_tickets(request:Request,q:str='',status:str=''):
    auth(request)
    return fetch('''SELECT t.*, e.title AS event_title,e.starts_at,e.venue,e.city,
        (SELECT l.status FROM listings l WHERE l.ticket_id=t.id ORDER BY l.id DESC LIMIT 1) AS listing_status
        FROM tickets t JOIN events e ON e.id=t.event_id
        WHERE (?='' OR t.status=?) AND (e.title LIKE ? OR t.section LIKE ? OR t.source LIKE ?)
        ORDER BY t.id DESC LIMIT 750''',
        (status,status,*(('%'+q[:100]+'%',)*3)))


@app.post('/api/tickets')
async def create_ticket(request:Request, event_id:int=Form(...), quantity:int=Form(1),
    section:str=Form(''), row_label:str=Form(''), seats:str=Form(''), source:str=Form(''),
    type:str=Form('E-Ticket'), cost:str=Form('0'), face:str=Form('0'),
    currency_code:str=Form('EUR'), notes:str=Form(''), file:UploadFile|None=File(None)):
    actor=auth(request,'operator',mutate=True)
    if quantity<1 or quantity>100:raise HTTPException(422,'Quantity must be 1–100.')
    if type not in ('E-Ticket','Mobile Transfer','Paper','Digital'):
        raise HTTPException(422,'Invalid ticket type.')
    document=None
    file_name=stored_name=sha=None
    if file and file.filename:
        raw=await file.read(MAX_FILE+1)
        if len(raw)>MAX_FILE:raise HTTPException(413,'Maximum PDF size is 20 MB.')
        if not raw.startswith(b'%PDF-') or not file.filename.lower().endswith('.pdf'):
            raise HTTPException(422,'Only valid PDF ticket files are supported.')
        sha=hashlib.sha256(raw).hexdigest()
        stored_name=uuid.uuid4().hex+'.bin'
        file_name=Path(file.filename).name[:160]
        document=CIPHER.encrypt(raw)
    with db(write=True) as conn:
        if not conn.execute('SELECT id FROM events WHERE id=? AND archived=0',(event_id,)).fetchone():
            raise HTTPException(404,'Event not found.')
        if sha and conn.execute('SELECT id FROM tickets WHERE event_id=? AND file_hash=?',(event_id,sha)).fetchone():
            raise HTTPException(409,'This exact PDF was already uploaded for this event.')
        if document:
            (VAULT/stored_name).write_bytes(document)
        try:
            cur=conn.execute('''INSERT INTO tickets(event_id,source,type,section,row_label,seats,quantity,
                cost_cents,face_cents,currency,status,notes,original_filename,stored_filename,file_hash,created_by,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (event_id,clean(source,80,False),type,clean(section,80,False),clean(row_label,60,False),
                clean(seats,150,False),quantity,amount_cents(cost),amount_cents(face),currency(currency_code),
                'available',clean(notes,1500,False),file_name,stored_name,sha,actor['id'],timestamp()))
            log(conn,actor['id'],'ticket.created','ticket',cur.lastrowid,f'event {event_id}, qty {quantity}')
            return {'id':cur.lastrowid}
        except Exception:
            if stored_name:(VAULT/stored_name).unlink(missing_ok=True)
            raise


@app.get('/api/tickets/{ticket_id}/pdf')
def ticket_download(ticket_id:int,request:Request):
    actor=auth(request)
    row=fetch('SELECT original_filename,stored_filename FROM tickets WHERE id=?',(ticket_id,),first=True)
    if not row or not row['stored_filename']:
        raise HTTPException(404,'Ticket PDF not found.')
    try:
        raw=CIPHER.decrypt((VAULT/row['stored_filename']).read_bytes())
    except (InvalidToken, FileNotFoundError):
        raise HTTPException(500,'Cannot decrypt this ticket. Check the backup of the encryption key.')
    filename=re.sub(r'[^a-zA-Z0-9._ -]','_',row['original_filename'] or 'ticket.pdf')
    return Response(raw,media_type='application/pdf',headers={
        'Content-Disposition': f'attachment; filename="{filename[:100]}"',
        'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})


class StatusPatch(BaseModel):
    status: Literal['available','reserved','cancelled']


@app.patch('/api/tickets/{ticket_id}/status')
def ticket_status(ticket_id:int,payload:StatusPatch,request:Request):
    actor=auth(request,'operator',mutate=True)
    with db(write=True) as conn:
        ticket=conn.execute('SELECT * FROM tickets WHERE id=?',(ticket_id,)).fetchone()
        if not ticket:raise HTTPException(404,'Ticket lot not found.')
        if ticket['sold_quantity']==ticket['quantity']:
            raise HTTPException(409,'All tickets in this lot are sold.')
        if payload.status=='cancelled' and conn.execute(
            "SELECT 1 FROM listings WHERE ticket_id=? AND status IN ('listed','review')",(ticket_id,)).fetchone():
            raise HTTPException(409,'Cancel any live marketplace listing first.')
        conn.execute('UPDATE tickets SET status=? WHERE id=?',(payload.status,ticket_id))
        log(conn,actor['id'],'ticket.status','ticket',ticket_id,payload.status)
    return {'ok':True}


class ListingInput(BaseModel):
    ticket_id:int
    marketplace: str = 'viagogo'
    price: str
    fee_pct: str = '10'
    notes: str = ''


@app.get('/api/listings')
def list_listings(request:Request):
    auth(request)
    return fetch('''SELECT l.*,t.quantity,t.sold_quantity,t.section,t.row_label,t.seats,
        t.status AS ticket_status,e.title AS event_title,e.starts_at
        FROM listings l JOIN tickets t ON t.id=l.ticket_id JOIN events e ON e.id=t.event_id
        ORDER BY l.id DESC LIMIT 600''')


@app.post('/api/listings')
def create_listing(payload:ListingInput,request:Request):
    actor=auth(request,'operator',mutate=True)
    with db(write=True) as conn:
        ticket=conn.execute('SELECT * FROM tickets WHERE id=?',(payload.ticket_id,)).fetchone()
        if not ticket:raise HTTPException(404,'Ticket not found.')
        if ticket['status']!='available' or ticket['sold_quantity']>=ticket['quantity']:
            raise HTTPException(409,'No available inventory in this lot.')
        try:
            cur=conn.execute('''INSERT INTO listings(ticket_id,marketplace,price_cents,commission_bp,
               currency,status,notes,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?)''',
               (payload.ticket_id,clean(payload.marketplace,50),amount_cents(payload.price),
                fee_basis_points(payload.fee_pct),ticket['currency'],'draft',clean(payload.notes,500,False),
                actor['id'],timestamp()))
        except sqlite3.IntegrityError:
            raise HTTPException(409,'An active listing already exists for this ticket lot.')
        log(conn,actor['id'],'listing.created','listing',cur.lastrowid)
        return {'id':cur.lastrowid}


class ListingPatch(BaseModel):
    status: Literal['draft','ready','listed','review','closed']
    external_id: str | None = None


@app.patch('/api/listings/{listing_id}')
def update_listing(listing_id:int,payload:ListingPatch,request:Request):
    actor=auth(request,'operator',mutate=True)
    with db(write=True) as conn:
        row=conn.execute('SELECT * FROM listings WHERE id=?',(listing_id,)).fetchone()
        if not row:raise HTTPException(404,'Listing not found.')
        if row['status']=='listed' and payload.status in ('draft','ready'):
            raise HTTPException(409,'Unlist on the marketplace before reverting a live listing.')
        if payload.status=='listed' and not payload.external_id:
            raise HTTPException(422,'For a manually listed offer, enter its marketplace listing ID.')
        conn.execute('UPDATE listings SET status=?,external_id=? WHERE id=?',
                     (payload.status,clean(payload.external_id,120,False) or row['external_id'],listing_id))
        log(conn,actor['id'],'listing.status','listing',listing_id,payload.status)
    return {'ok':True}


class SaleInput(BaseModel):
    ticket_id:int
    listing_id:int | None = None
    quantity:int=Field(ge=1,le=100)
    amount:str
    fees:str='0'
    channel:str='viagogo'
    reference:str=''
    sold_at:str | None = None


@app.get('/api/sales')
def list_sales(request:Request):
    auth(request)
    return fetch('''SELECT s.*,e.title AS event_title,t.section,t.row_label,t.seats,
        t.cost_cents AS unit_cost_cents FROM sales s JOIN tickets t ON t.id=s.ticket_id
        JOIN events e ON e.id=t.event_id ORDER BY s.sold_at DESC LIMIT 700''')


@app.post('/api/sales')
def create_sale(payload:SaleInput,request:Request):
    actor=auth(request,'operator',mutate=True)
    with db(write=True) as conn:
        ticket=conn.execute('SELECT * FROM tickets WHERE id=?',(payload.ticket_id,)).fetchone()
        if not ticket:raise HTTPException(404,'Ticket not found.')
        available=ticket['quantity']-ticket['sold_quantity']
        if payload.quantity>available or ticket['status']=='cancelled':
            raise HTTPException(409,f'Only {available} ticket(s) remain in this lot.')
        listing_id=payload.listing_id
        if listing_id:
            li=conn.execute('SELECT ticket_id FROM listings WHERE id=?',(listing_id,)).fetchone()
            if not li or li['ticket_id']!=payload.ticket_id:
                raise HTTPException(422,'Listing does not belong to selected ticket lot.')
        if amount_cents(payload.fees)>amount_cents(payload.amount):
            raise HTTPException(422,'Fees cannot exceed sale amount.')
        cur=conn.execute('''INSERT INTO sales(ticket_id,listing_id,quantity,amount_cents,fee_cents,
            channel,reference,sold_at,currency,created_by,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
            (payload.ticket_id,listing_id,payload.quantity,amount_cents(payload.amount),
             amount_cents(payload.fees),clean(payload.channel,80),clean(payload.reference,120,False),
             parse_date(payload.sold_at or timestamp()),ticket['currency'],actor['id'],timestamp()))
        new_sold=ticket['sold_quantity']+payload.quantity
        conn.execute('UPDATE tickets SET sold_quantity=?,status=? WHERE id=?',
                     (new_sold,'sold' if new_sold==ticket['quantity'] else ticket['status'],payload.ticket_id))
        if new_sold==ticket['quantity']:
            conn.execute("UPDATE listings SET status='closed' WHERE ticket_id=? AND status IN ('draft','ready','listed','review')",
                         (payload.ticket_id,))
        log(conn,actor['id'],'sale.created','sale',cur.lastrowid,f'qty {payload.quantity}')
        return {'id':cur.lastrowid}


class ExpenseInput(BaseModel):
    event_id:int | None = None
    label:str
    amount:str
    currency:str='EUR'
    incurred_at:str | None = None
    notes:str=''


@app.get('/api/expenses')
def list_expenses(request:Request):
    auth(request)
    return fetch('''SELECT x.*,e.title AS event_title FROM expenses x
        LEFT JOIN events e ON e.id=x.event_id ORDER BY x.id DESC LIMIT 600''')


@app.post('/api/expenses')
def create_expense(payload:ExpenseInput,request:Request):
    actor=auth(request,'operator',mutate=True)
    with db(write=True) as conn:
        if payload.event_id and not conn.execute('SELECT id FROM events WHERE id=?',(payload.event_id,)).fetchone():
            raise HTTPException(404,'Event not found.')
        cur=conn.execute('''INSERT INTO expenses(event_id,label,amount_cents,currency,incurred_at,
          notes,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)''',
          (payload.event_id,clean(payload.label,160),amount_cents(payload.amount),currency(payload.currency),
           parse_date(payload.incurred_at or timestamp()),clean(payload.notes,500,False),actor['id'],timestamp()))
        log(conn,actor['id'],'expense.created','expense',cur.lastrowid)
        return {'id':cur.lastrowid}


@app.get('/api/dashboard')
def dashboard(request:Request):
    auth(request)
    # Currency groups are not combined in monetary metrics; default EUR dashboard.
    with db() as conn:
        events=conn.execute('SELECT count(*) FROM events WHERE archived=0').fetchone()[0]
        inventory=conn.execute('''SELECT COUNT(*),COALESCE(SUM(quantity),0),
            COALESCE(SUM(CASE WHEN status='available' THEN quantity-sold_quantity ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN status='available' THEN (quantity-sold_quantity)*cost_cents ELSE 0 END),0)
            FROM tickets WHERE status!='cancelled' AND currency='EUR' ''').fetchone()
        revenue=conn.execute("SELECT COALESCE(SUM(amount_cents),0),COALESCE(SUM(fee_cents),0) FROM sales WHERE currency='EUR'").fetchone()
        sold_cost=conn.execute('''SELECT COALESCE(SUM(s.quantity*t.cost_cents),0)
            FROM sales s JOIN tickets t ON t.id=s.ticket_id WHERE s.currency='EUR' ''').fetchone()[0]
        expenses=conn.execute("SELECT COALESCE(SUM(amount_cents),0) FROM expenses WHERE currency='EUR'").fetchone()[0]
        listing_counts={r['status']:r['n'] for r in conn.execute('SELECT status,COUNT(*) AS n FROM listings GROUP BY status')}
        upcoming=[dict(x) for x in conn.execute('''SELECT e.id,e.title,e.starts_at,e.venue,e.city,
            COALESCE(SUM(t.quantity-t.sold_quantity),0) AS remaining
            FROM events e LEFT JOIN tickets t ON t.event_id=e.id
            WHERE e.archived=0 AND e.starts_at >= ? GROUP BY e.id
            ORDER BY e.starts_at ASC LIMIT 7''',(timestamp(),))]
        activity=[dict(x) for x in conn.execute('''SELECT a.created_at,a.action,a.entity,a.entity_id,u.name AS actor
            FROM audit a LEFT JOIN users u ON a.user_id=u.id ORDER BY a.id DESC LIMIT 10''')]
    return {'events':events,'lots':inventory[0],'tickets_total':inventory[1],
        'tickets_available':inventory[2],'inventory_value_cents':inventory[3],
        'sales_revenue_cents':revenue[0], 'sales_fees_cents':revenue[1],
        'gross_profit_cents':revenue[0]-revenue[1]-sold_cost-expenses,
        'expenses_cents':expenses,'listing_status':listing_counts,
        'upcoming':upcoming,'activity':activity,'currency':'EUR',
        'note':'Monetary KPI totals include EUR transactions only; other currencies are kept separate.'}



def event_financial_summary(conn, event_row):
    event_id=event_row['id']
    tickets=conn.execute("""SELECT COALESCE(SUM(quantity),0) AS qty,
        COALESCE(SUM(sold_quantity),0) AS sold,
        COALESCE(SUM(CASE WHEN currency='EUR' THEN quantity*cost_cents ELSE 0 END),0) AS inventory_cost_cents
        FROM tickets WHERE event_id=?""",(event_id,)).fetchone()
    sales=conn.execute("""SELECT COALESCE(SUM(s.amount_cents),0) AS revenue,
        COALESCE(SUM(s.fee_cents),0) AS fees,
        COALESCE(SUM(CASE WHEN t.currency='EUR' THEN s.quantity*t.cost_cents ELSE 0 END),0) AS sold_cost,
        COUNT(*) AS transactions
        FROM sales s JOIN tickets t ON t.id=s.ticket_id
        WHERE t.event_id=? AND s.currency='EUR'""",(event_id,)).fetchone()
    expenses=conn.execute("""SELECT COALESCE(SUM(amount_cents),0) AS expenses FROM expenses
        WHERE event_id=? AND currency='EUR'""",(event_id,)).fetchone()['expenses']
    invested=sales['sold_cost']+expenses
    net=sales['revenue']-sales['fees']-invested
    return {
        'id':event_id,'title':event_row['title'],'starts_at':event_row['starts_at'],
        'venue':event_row['venue'],'city':event_row['city'],'country':event_row['country'],
        'quantity':tickets['qty'],'sold':tickets['sold'],'remaining':tickets['qty']-tickets['sold'],
        'inventory_cost_cents':tickets['inventory_cost_cents'],
        'sold_cost_cents':sales['sold_cost'],'revenue_cents':sales['revenue'],
        'fees_cents':sales['fees'],'expenses_cents':expenses,
        'net_profit_cents':net,'roi_pct':round(net*100/invested,1) if invested else None,
        'transactions':sales['transactions'],
        'currency':'EUR','currency_note':'Summary includes only EUR tickets/sales/expenses.'
    }


@app.get('/api/insights')
def insights(request:Request):
    auth(request)
    with db() as conn:
        events=conn.execute('SELECT * FROM events ORDER BY starts_at DESC LIMIT 300').fetchall()
        summaries=[event_financial_summary(conn,e) for e in events]
        months=conn.execute("""SELECT substr(sold_at,1,7) AS month,
            SUM(amount_cents) AS revenue_cents,SUM(fee_cents) AS fees_cents,
            COUNT(*) AS transactions
            FROM sales WHERE currency='EUR'
            GROUP BY substr(sold_at,1,7) ORDER BY month DESC LIMIT 12""").fetchall()
    ranked=sorted((x for x in summaries if x['sold']>0),key=lambda x:x['net_profit_cents'],reverse=True)
    return {'top_events':ranked[:8], 'event_performance':summaries[:150],
            'monthly_sales':list(reversed([dict(x) for x in months])),
            'currency':'EUR','note':'ROI = (EUR revenue - fees - sold ticket cost - EUR event expenses) / (sold ticket cost + EUR event expenses).'}


@app.get('/api/events/{event_id}/recap')
def event_recap(event_id:int,request:Request):
    auth(request)
    with db() as conn:
        event=conn.execute('SELECT * FROM events WHERE id=?',(event_id,)).fetchone()
        if not event:raise HTTPException(404,'Event not found.')
        summary=event_financial_summary(conn,event)
        sales=[dict(x) for x in conn.execute("""SELECT s.quantity,s.amount_cents,s.fee_cents,
            s.sold_at,s.channel,s.currency,t.section,t.row_label,t.seats
            FROM sales s JOIN tickets t ON t.id=s.ticket_id
            WHERE t.event_id=? ORDER BY s.sold_at DESC LIMIT 100""",(event_id,))]
    return {'summary':summary,'sales':sales}


@app.get('/api/audit')
def audit_log(request:Request):
    auth(request,'manager')
    return fetch('''SELECT a.*,u.name AS actor FROM audit a LEFT JOIN users u ON u.id=a.user_id
        ORDER BY a.id DESC LIMIT 300''')


def escape_csv(value):
    text=str(value if value is not None else '')
    return "'"+text if text.lstrip().startswith(('=','+','-','@','\t','\r')) else text


@app.get('/api/export/{kind}.csv')
def export_csv(kind:str,request:Request):
    auth(request,'manager')
    if kind=='tickets':
        data=fetch('''SELECT t.id,e.title as event,t.section,t.row_label,t.seats,t.quantity,
           t.sold_quantity,t.source,t.status,t.cost_cents,t.currency,t.created_at FROM tickets t
           JOIN events e ON e.id=t.event_id ORDER BY t.id''')
    elif kind=='sales':
        data=fetch('''SELECT s.id,e.title AS event,s.quantity,s.amount_cents,s.fee_cents,s.channel,
            s.sold_at,s.currency FROM sales s JOIN tickets t ON t.id=s.ticket_id
            JOIN events e ON e.id=t.event_id ORDER BY s.id''')
    else:
        raise HTTPException(404,'Unknown export type.')
    buffer=io.StringIO()
    fields=list(data[0]) if data else (['id','event','quantity','status'] if kind=='tickets' else ['id','event','quantity','amount_cents'])
    writer=csv.DictWriter(buffer,fieldnames=fields)
    writer.writeheader()
    for row in data:writer.writerow({k:escape_csv(v) for k,v in row.items()})
    return Response(buffer.getvalue(),media_type='text/csv; charset=utf-8',headers={
        'Content-Disposition':f'attachment; filename="ticketwave-{kind}.csv"'})


class WatchInput(BaseModel):
    keyword:str=Field(min_length=2,max_length=100)
    country:str=''


@app.get('/api/watchlist')
def watchlist(request:Request):
    auth(request)
    return fetch('SELECT * FROM watchlist ORDER BY id DESC')


@app.post('/api/watchlist')
def add_watch(payload:WatchInput,request:Request):
    actor=auth(request,'manager',mutate=True)
    code=payload.country.strip().upper()
    if code and not re.fullmatch('[A-Z]{2}',code):
        raise HTTPException(422,'Country must be a two-letter code, e.g. SK, CZ, GB.')
    with db(write=True) as conn:
        cur=conn.execute('''INSERT INTO watchlist(keyword,country,created_at,created_by)
            VALUES(?,?,?,?)''',(clean(payload.keyword,100),code,timestamp(),actor['id']))
        log(conn,actor['id'],'watchlist.created','watchlist',cur.lastrowid,payload.keyword)
        return {'id':cur.lastrowid}


@app.delete('/api/watchlist/{watch_id}')
def delete_watch(watch_id:int,request:Request):
    actor=auth(request,'manager',mutate=True)
    with db(write=True) as conn:
        if not conn.execute('DELETE FROM watchlist WHERE id=?',(watch_id,)).rowcount:
            raise HTTPException(404,'Watch item not found.')
        log(conn,actor['id'],'watchlist.removed','watchlist',watch_id)
    return {'ok':True}


def integration_secret(user_id: int, provider: str):
    row = fetch('SELECT value_enc FROM integration_secrets WHERE user_id=? AND provider=?',
                (user_id, provider), first=True)
    if not row:
        return None
    try:
        return json.loads(CIPHER.decrypt(row['value_enc']).decode('utf-8'))
    except (InvalidToken, ValueError, UnicodeDecodeError):
        raise HTTPException(500, 'Saved integration secret could not be decrypted. Restore the matching encryption key backup.')


def write_integration_secret(user_id: int, provider: str, value: dict):
    sealed = CIPHER.encrypt(json.dumps(value).encode('utf-8'))
    with db(write=True) as conn:
        conn.execute('''INSERT INTO integration_secrets(user_id,provider,value_enc,updated_at)
            VALUES(?,?,?,?) ON CONFLICT(user_id,provider) DO UPDATE SET
            value_enc=excluded.value_enc,updated_at=excluded.updated_at''',
            (user_id, provider, sealed, timestamp()))
        log(conn,user_id,'integration.saved','integration',None,provider)


def tm_key(user_id=None):
    if user_id:
        config=integration_secret(user_id,'ticketmaster')
        if config and config.get('api_key'):
            return config['api_key']
    return os.environ.get('TICKETMASTER_API_KEY','')


async def tm_fetch(key, *, keyword='', country='', city='', limit=12):
    params={'apikey':key,'size':min(limit,40),'sort':'date,asc'}
    if keyword: params['keyword']=keyword[:100]
    if country: params['countryCode']=country
    if city: params['city']=city[:100]
    try:
        async with httpx.AsyncClient(timeout=18.0) as client:
            r=await client.get('https://app.ticketmaster.com/discovery/v2/events.json',params=params)
        if r.status_code in (400,401,403):
            raise HTTPException(422,'Ticketmaster rejected this API key or search filters. Check your key in Integrations.')
        if r.status_code==429:
            raise HTTPException(429,'Ticketmaster rate limit reached. Please retry later.')
        r.raise_for_status()
        data=r.json()
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502,'Ticketmaster Discovery is temporarily unavailable.')
    results=[]
    for item in (data.get('_embedded') or {}).get('events',[]):
        date=(item.get('dates') or {}).get('start') or {}
        venue=((item.get('_embedded') or {}).get('venues') or [{}])[0]
        dt=date.get('dateTime')
        if not dt: continue
        images=item.get('images') or []
        cover=next((i.get('url') for i in images if i.get('ratio')=='16_9' and i.get('width',0)>=600),None)
        results.append({'external_id':item.get('id'), 'title':item.get('name'),
            'starts_at':dt, 'venue':venue.get('name') or 'TBA',
            'city':(venue.get('city') or {}).get('name') or 'TBA',
            'country':(venue.get('country') or {}).get('name') or 'TBA',
            'source':'ticketmaster','url':item.get('url'),'image':cover})
    return results


async def discovery_search(keyword, country='', limit=12, user_id=None, city=''):
    key=tm_key(user_id)
    if not key:
        raise HTTPException(412,'Ticketmaster Discovery API is not configured for this workspace.')
    return await tm_fetch(key,keyword=keyword,country=country,city=city,limit=limit)


@app.get('/api/discovery')
async def discovery(request:Request,q:str='',country:str='',city:str=''):
    user=auth(request)
    q=q.strip();city=city.strip();country=country.strip().upper()
    if len(q)<2 and len(city)<2:
        raise HTTPException(422,'Enter an artist, event or city (at least two characters).')
    if country and not re.fullmatch(r'[A-Z]{2}',country):
        raise HTTPException(422,'Country code must have two letters (SK, CZ, GB, US).')
    return await discovery_search(q,country,24,user_id=user['id'],city=city)


class ImportEvent(BaseModel):
    external_id:str
    title:str
    starts_at:str
    venue:str
    city:str
    country:str


@app.post('/api/discovery/import')
def import_discovery(payload:ImportEvent,request:Request):
    actor=auth(request,'operator',mutate=True)
    if not tm_key(actor['id']):
        raise HTTPException(412,'Connect Ticketmaster first under Integrations.')
    with db(write=True) as conn:
        found=conn.execute("SELECT id FROM events WHERE external_source='ticketmaster' AND external_id=?",(payload.external_id,)).fetchone()
        if found:return {'id':found['id'],'existing':True}
        cur=conn.execute('''INSERT INTO events(title,starts_at,venue,city,country,category,
              external_source,external_id,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)''',
              (clean(payload.title,180),parse_date(payload.starts_at),clean(payload.venue,180),
              clean(payload.city,100),clean(payload.country,60),'Concert',
              'ticketmaster',clean(payload.external_id,100),actor['id'],timestamp()))
        log(conn,actor['id'],'event.imported','event',cur.lastrowid)
        return {'id':cur.lastrowid,'existing':False}


async def sync_watchlist():
    if not (os.environ.get('TICKETMASTER_API_KEY') or fetch("SELECT 1 AS yes FROM integration_secrets WHERE provider='ticketmaster' LIMIT 1",first=True)):
        raise HTTPException(412,'No Ticketmaster integration configured.')
    watched=fetch('SELECT * FROM watchlist WHERE enabled=1 LIMIT 30')
    added=0
    for watch in watched:
        try:
            matches=await discovery_search(watch['keyword'],watch['country'],limit=8,user_id=watch['created_by'])
            with db(write=True) as conn:
                for item in matches:
                    try:
                        cur=conn.execute('''INSERT INTO events(title,starts_at,venue,city,country,category,
                            external_source,external_id,created_by,created_at)
                            VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING''',
                            (clean(item['title'],180),parse_date(item['starts_at']),
                             clean(item['venue'],180),clean(item['city'],100),clean(item['country'],60),
                             'Concert','ticketmaster',item['external_id'],watch['created_by'],timestamp()))
                        added+=cur.rowcount
                    except HTTPException:
                        continue
                conn.execute("UPDATE watchlist SET last_synced=?,last_error='' WHERE id=?",(timestamp(),watch['id']))
            await asyncio.sleep(.25)
        except Exception as e:
            with db(write=True) as conn:
                conn.execute('UPDATE watchlist SET last_error=? WHERE id=?',(str(e)[:200],watch['id']))
    return {'watched':len(watched),'added':added}


@app.post('/api/watchlist/sync')
async def sync_now(request:Request):
    actor=auth(request,'manager',mutate=True)
    result=await sync_watchlist()
    with db(write=True) as conn:
        log(conn,actor['id'],'watchlist.synced','watchlist',None,json.dumps(result))
    return result


# All credentials and OAuth tokens are encrypted at rest and never returned in API responses.
class TicketmasterKeyInput(BaseModel):
    api_key: str=Field(min_length=8,max_length=200)


@app.put('/api/integrations/ticketmaster')
async def connect_tm(payload:TicketmasterKeyInput, request:Request):
    actor=auth(request,'viewer',mutate=True)
    key=payload.api_key.strip()
    if not re.fullmatch(r'[A-Za-z0-9._-]{8,200}',key):
        raise HTTPException(422,'Invalid API key format.')
    # Probe the official provider before saving: no fake connection states.
    await tm_fetch(key,keyword='concert',limit=1)
    write_integration_secret(actor['id'],'ticketmaster',{'api_key':key})
    return {'connected':True,'message':'Ticketmaster API key validated and saved securely.'}


@app.delete('/api/integrations/ticketmaster')
def disconnect_tm(request:Request):
    actor=auth(request,'viewer',mutate=True)
    with db(write=True) as conn:
        conn.execute('DELETE FROM integration_secrets WHERE user_id=? AND provider=?',
                    (actor['id'],'ticketmaster'))
        log(conn,actor['id'],'integration.deleted','integration',None,'ticketmaster')
    return {'ok':True}


class ViagogoAppInput(BaseModel):
    client_id: str=Field(min_length=4,max_length=300)
    client_secret: str=Field(min_length=8,max_length=500)


@app.put('/api/integrations/viagogo/app')
def save_viagogo_app(payload:ViagogoAppInput,request:Request):
    actor=auth(request,'viewer',mutate=True)
    write_integration_secret(actor['id'],'viagogo_app',{
        'client_id':payload.client_id.strip(),
        'client_secret':payload.client_secret.strip()
    })
    return {'configured':True,'message':'Viagogo app credentials encrypted on the server. Sign in with Viagogo next.'}


@app.delete('/api/integrations/viagogo')
def disconnect_viagogo(request:Request):
    actor=auth(request,'viewer',mutate=True)
    with db(write=True) as conn:
        conn.execute('DELETE FROM integration_secrets WHERE user_id=? AND provider IN (?,?)',
                    (actor['id'],'viagogo_app','viagogo_token'))
        conn.execute('DELETE FROM oauth_pending WHERE user_id=?',(actor['id'],))
        log(conn,actor['id'],'integration.deleted','integration',None,'viagogo')
    return {'ok':True}


@app.post('/api/integrations/viagogo/authorize')
def viagogo_authorize(request:Request):
    actor=auth(request,'viewer',mutate=True)
    client=integration_secret(actor['id'],'viagogo_app')
    if not client:
        raise HTTPException(412,'First save your Viagogo Client ID and Client Secret.')
    base=os.environ.get('CTW_PUBLIC_BASE_URL',str(request.base_url)).rstrip('/')
    # HTTPS is required by Viagogo, including test accounts; don't allow insecure OAuth.
    if not base.startswith('https://') or any(x in base for x in ('?', '#', '@')):
        raise HTTPException(412,'Viagogo OAuth requires an HTTPS-hosted app and registered HTTPS callback URL.')
    redirect_uri=base+'/api/integrations/viagogo/callback'
    state=secrets.token_urlsafe(40)
    state_hash=hashlib.sha256(state.encode()).hexdigest()
    with db(write=True) as conn:
        conn.execute('DELETE FROM oauth_pending WHERE expires_at<?',(timestamp(),))
        conn.execute('INSERT INTO oauth_pending(state_hash,user_id,redirect_uri,expires_at) VALUES(?,?,?,?)',
                     (state_hash,actor['id'],redirect_uri,(utcnow()+timedelta(minutes=10)).isoformat()))
    url='https://account.viagogo.com/authorize?'+urlencode({
        'client_id':client['client_id'],'response_type':'code','redirect_uri':redirect_uri,
        'scope':'read:sellerlistings write:sellerlistings read:events read:sales','state':state
    })
    return {'authorization_url':url, 'callback_url':redirect_uri}


@app.get('/api/integrations/viagogo/callback')
async def viagogo_callback(state:str='',code:str='',error:str=''):
    if not state or not code or error:
        return RedirectResponse('/?#integrations',status_code=303)
    state_hash=hashlib.sha256(state.encode()).hexdigest()
    with db(write=True) as conn:
        pending=conn.execute('SELECT * FROM oauth_pending WHERE state_hash=?',(state_hash,)).fetchone()
        if not pending or pending['expires_at']<timestamp():
            raise HTTPException(400,'Viagogo authorization expired; please reconnect.')
        conn.execute('DELETE FROM oauth_pending WHERE state_hash=?',(state_hash,))
    client=integration_secret(pending['user_id'],'viagogo_app')
    if not client:
        raise HTTPException(412,'Viagogo app configuration is missing.')
    try:
        async with httpx.AsyncClient(timeout=20.0) as http:
            r=await http.post('https://account.viagogo.com/oauth2/token',
                auth=(client['client_id'],client['client_secret']),
                data={'grant_type':'authorization_code','code':code,
                    'redirect_uri':pending['redirect_uri'],
                    'scope':'read:sellerlistings write:sellerlistings read:events read:sales'})
        if r.status_code!=200:
            raise HTTPException(502,'Viagogo declined OAuth token exchange. Check your app settings and callback URL.')
        token=r.json()
        if not token.get('access_token'):
            raise HTTPException(502,'Viagogo did not return a usable access token.')
    except httpx.HTTPError:
        raise HTTPException(502,'Viagogo authentication service is unavailable.')
    write_integration_secret(pending['user_id'],'viagogo_token',{
        'access_token':token['access_token'],
        'refresh_token':token.get('refresh_token',''),
        'scope':token.get('scope',''),
        'expires_at':(utcnow()+timedelta(seconds=max(60,int(token.get('expires_in',3600))-45))).isoformat()
    })
    return RedirectResponse('/?#integrations',status_code=303)


async def viagogo_user_token(user_id):
    token=integration_secret(user_id,'viagogo_token')
    if not token:
        raise HTTPException(412,'Connect your Viagogo account under Integrations.')
    if token.get('expires_at','')>timestamp():
        return token['access_token']
    client=integration_secret(user_id,'viagogo_app')
    if not client or not token.get('refresh_token'):
        raise HTTPException(412,'Viagogo authorization expired. Reconnect your account.')
    try:
        async with httpx.AsyncClient(timeout=20.0) as http:
            r=await http.post('https://account.viagogo.com/oauth2/token',
                auth=(client['client_id'],client['client_secret']),
                data={'grant_type':'refresh_token','refresh_token':token['refresh_token']})
        if r.status_code!=200:
            raise HTTPException(412,'Viagogo session has expired. Reconnect your account.')
        updated=r.json()
    except httpx.HTTPError:
        raise HTTPException(502,'Viagogo authentication service is unavailable.')
    token={**token,'access_token':updated['access_token'],
         'refresh_token':updated.get('refresh_token',token['refresh_token']),
         'scope':updated.get('scope',token.get('scope','')),
         'expires_at':(utcnow()+timedelta(seconds=max(60,int(updated.get('expires_in',3600))-45))).isoformat()}
    write_integration_secret(user_id,'viagogo_token',token)
    return token['access_token']


@app.get('/api/integrations/viagogo/listings')
async def viagogo_listings(request:Request):
    actor=auth(request)
    token=await viagogo_user_token(actor['id'])
    try:
        async with httpx.AsyncClient(timeout=20.0) as http:
            r=await http.get('https://api.viagogo.net/v2/sellerlistings',
                headers={'Authorization':'Bearer '+token,'Accept':'application/hal+json',
                         'User-Agent':'C-TicketWave-PRO/4.0'})
        if r.status_code in (401,403):
            raise HTTPException(403,'Viagogo denied access to seller listings. Check OAuth scopes and seller permissions.')
        r.raise_for_status()
        data=r.json()
        return {'total_items':data.get('total_items',0),
                'items':(data.get('_embedded') or {}).get('items',[])[:20]}
    except HTTPException:
        raise
    except (httpx.HTTPError,ValueError):
        raise HTTPException(502,'Could not read Viagogo listings at this time.')


@app.get('/api/integrations')
def integrations(request:Request):
    actor=auth(request)
    user_id=actor['id']
    viagogo_app=integration_secret(user_id,'viagogo_app')
    viagogo_token=integration_secret(user_id,'viagogo_token')
    personal_tm=integration_secret(user_id,'ticketmaster')
    return {
        'ticketmaster_discovery':bool(tm_key(user_id)),
        'ticketmaster_source':'personal' if personal_tm else ('server' if tm_key() else 'none'),
        'viagogo':{'status':'connected' if viagogo_token else ('app_configured' if viagogo_app else 'not_configured'),
                   'app_configured':bool(viagogo_app),
                   'connected':bool(viagogo_token),
                   'scopes':viagogo_token.get('scope','') if viagogo_token else '',
                   'description':'Individual OAuth connection with encrypted tokens. Marketplace publishing remains disabled until seller eligibility and production mapping are validated.',
                   'developer_url':'https://developer.viagogo.net/'},
        'workspace':'Single trusted team, local SQLite storage',
        'secure_cookies':SECURE_COOKIE
    }


@app.get('/health')
def health():
    return {'status':'ok'}
