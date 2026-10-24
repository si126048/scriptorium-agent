"""OIDC authorization-code/PKCE login, opaque server sessions and scoped API credentials."""
import base64
import hashlib
import json
import os
import secrets
from urllib.parse import urlencode
import httpx
import jwt
import sqlalchemy as sa
from fastapi import Depends, Header, Request
from fastapi.responses import RedirectResponse, JSONResponse
from . import schema as db
from .service import ResearchError, row

COOKIE = 'scriptorium_session'


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def issuer():
    return os.getenv('SCRIPTORIUM_OIDC_ISSUER', '').rstrip('/')


def metadata():
    with httpx.Client(timeout=10, trust_env=False) as client:
        r = client.get(issuer() + '/.well-known/openid-configuration'); r.raise_for_status()
        value = r.json()
    if value['issuer'].rstrip('/') != issuer():
        raise ResearchError('OIDC_ISSUER_MISMATCH', 503)
    return value


def principal(request, settings, service, authorization):
    if authorization.startswith('Bearer ') and issuer() and not request.cookies.get(COOKIE):
        try:
            token = authorization[7:]
            cfg = metadata()
            key = jwt.PyJWKClient(cfg['jwks_uri']).get_signing_key_from_jwt(token)
            claims = jwt.decode(token, key.key, algorithms=['RS256', 'ES256'], audience=os.environ['SCRIPTORIUM_OIDC_CLIENT_ID'], issuer=cfg['issuer'])
            return 'oidc:' + digest(cfg['issuer'] + '\0' + claims['sub'])[:48]
        except Exception:
            raise ResearchError('INVALID_ACCESS_TOKEN', 401) from None
    cookie = request.cookies.get(COOKIE)
    if cookie and issuer():
        with service.engine.connect() as c:
            session = row(c, db.sessions, db.sessions.c.id == digest(cookie), db.sessions.c.expires_at > db.now())
        if not session:
            raise ResearchError('SESSION_EXPIRED', 401)
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            expected = os.getenv('SCRIPTORIUM_PUBLIC_URL', '').rstrip('/')
            if request.headers.get('origin') != expected:
                raise ResearchError('SESSION_ORIGIN_REQUIRED', 403)
        return session['user_id']
    if issuer():
        raise ResearchError('LOGIN_REQUIRED', 401)
    return None


def install(app, service, identity):
    @app.get('/api/v2/auth/session')
    def session(request: Request, authorization: str = Header(default=''), s=Depends(service)):
        if not issuer():
            return {'mode': 'local', 'authenticated': True, 'user_id': s.settings.principal, 'name': '本机研究者'}
        try:
            actor = principal(request, s.settings, s, authorization)
            with s.engine.connect() as c:
                user = row(c, db.users, db.users.c.id == actor)
            return {'mode': 'oidc', 'authenticated': True, 'user_id': actor, 'name': (user or {}).get('name', actor)}
        except ResearchError:
            return {'mode': 'oidc', 'authenticated': False}

    @app.get('/api/v2/auth/login')
    def login(s=Depends(service)):
        if not issuer():
            raise ResearchError('OIDC_NOT_CONFIGURED', 409)
        cfg = metadata(); state = secrets.token_urlsafe(32); verifier = secrets.token_urlsafe(48)
        nonce = secrets.token_urlsafe(32)
        with s.engine.begin() as c:
            # Short-lived state is stored server-side; the cookie only binds this browser.
            c.execute(db.users.insert().values(id='flow:' + state, name=json.dumps({'verifier': verifier, 'nonce': nonce}), created_at=db.now()))
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        url = cfg['authorization_endpoint'] + '?' + urlencode({'client_id': os.environ['SCRIPTORIUM_OIDC_CLIENT_ID'],
            'redirect_uri': os.environ['SCRIPTORIUM_PUBLIC_URL'].rstrip('/') + '/api/v2/auth/callback',
            'response_type': 'code', 'scope': 'openid profile', 'state': state, 'nonce': nonce,
            'code_challenge': challenge, 'code_challenge_method': 'S256'})
        r = RedirectResponse(url); r.set_cookie('scriptorium_oidc_state', state, max_age=600, httponly=True, secure=os.getenv('SCRIPTORIUM_COOKIE_SECURE', '1') == '1', samesite='lax')
        return r

    @app.get('/api/v2/auth/callback')
    def callback(request: Request, state: str, code: str, s=Depends(service)):
        if not secrets.compare_digest(request.cookies.get('scriptorium_oidc_state', ''), state):
            raise ResearchError('OIDC_STATE_MISMATCH', 401)
        with s.engine.begin() as c:
            flow = c.execute(sa.select(db.users).where(db.users.c.id == 'flow:' + state).with_for_update()).mappings().first()
            if not flow or flow['created_at'] < db.now() - 600:
                raise ResearchError('OIDC_STATE_EXPIRED', 401)
            c.execute(db.users.delete().where(db.users.c.id == flow['id']))
        values = json.loads(flow['name']); cfg = metadata()
        with httpx.Client(timeout=20, trust_env=False) as client:
            r = client.post(cfg['token_endpoint'], data={'grant_type': 'authorization_code', 'code': code,
                'client_id': os.environ['SCRIPTORIUM_OIDC_CLIENT_ID'], 'code_verifier': values['verifier'],
                'redirect_uri': os.environ['SCRIPTORIUM_PUBLIC_URL'].rstrip('/') + '/api/v2/auth/callback'})
            r.raise_for_status(); token = r.json()['id_token']
        key = jwt.PyJWKClient(cfg['jwks_uri']).get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=['RS256', 'ES256'], audience=os.environ['SCRIPTORIUM_OIDC_CLIENT_ID'], issuer=cfg['issuer'])
        if claims.get('nonce') != values['nonce']:
            raise ResearchError('OIDC_NONCE_MISMATCH', 401)
        uid = 'oidc:' + digest(cfg['issuer'] + '\0' + claims['sub'])[:48]; secret = secrets.token_urlsafe(48)
        with s.engine.begin() as c:
            from sqlalchemy.dialects.postgresql import insert
            c.execute(insert(db.users).values(id=uid, name=str(claims.get('name') or claims.get('preferred_username') or uid), created_at=db.now()).on_conflict_do_nothing())
            c.execute(db.sessions.insert().values(id=digest(secret), user_id=uid, expires_at=db.now() + 28800))
        r = RedirectResponse(os.environ['SCRIPTORIUM_PUBLIC_URL'].rstrip('/') + '/')
        r.set_cookie(COOKIE, secret, max_age=28800, httponly=True, secure=os.getenv('SCRIPTORIUM_COOKIE_SECURE', '1') == '1', samesite='lax')
        r.delete_cookie('scriptorium_oidc_state'); return r

    @app.post('/api/v2/auth/logout')
    def logout(request: Request, actor=Depends(identity), s=Depends(service)):
        with s.engine.begin() as c:
            c.execute(db.sessions.delete().where(db.sessions.c.id == digest(request.cookies.get(COOKIE, ''))))
        r = JSONResponse({'logged_out': True}); r.delete_cookie(COOKIE); return r
