from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque
import hashlib, secrets, hmac, time
import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from app.core.config import settings, PROTOTYPE
from app.core.db import get_db
from app.core.models import User, Case, Assignment
from app.core.enums import Role
from app.core.errors import DomainError, require

bearer = HTTPBearer(auto_error=False)
def hash_password(password):
    salt = secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return f'scrypt${salt.hex()}${value.hex()}'

def password_matches(password, stored):
    try:
        _, salt, expected = stored.split('$')
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError): return False

def issue_token(subject, kind, role=None):
    ttl = settings.jwt_ttl_minutes if kind == 'officer' else PROTOTYPE['auth']['citizen_session_minutes']
    payload = {'sub': subject, 'typ': kind, 'iss': 'e-maap', 'aud': 'e-maap-clients',
        'iat': datetime.now(timezone.utc), 'exp': datetime.now(timezone.utc) + timedelta(minutes=ttl), 'jti': secrets.token_hex(16)}
    if role: payload['role'] = str(role)
    return jwt.encode(payload, settings.jwt_secret, algorithm='HS256')

@dataclass
class Actor:
    subject: str
    kind: str
    role: str | None = None
    name: str = 'Citizen'
    @property
    def user_id(self): return self.subject if self.kind == 'officer' else None

def actor(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db=Depends(get_db)):
    if not credentials: raise DomainError('AUTH_REQUIRED', 'Sign in to continue.', 401)
    try:
        claims = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=['HS256'], audience='e-maap-clients', issuer='e-maap')
        result = Actor(claims['sub'], claims['typ'], claims.get('role'))
    except (jwt.InvalidTokenError, KeyError):
        raise DomainError('AUTH_REQUIRED', 'Your session has expired. Sign in again.', 401)
    if result.kind == 'officer':
        user = db.get(User, result.subject)
        if not user or not user.active or str(user.role) != result.role:
            raise DomainError('AUTH_REQUIRED', 'This session is no longer authorised.', 401)
        result.name = user.name
    elif result.kind != 'citizen': raise DomainError('AUTH_REQUIRED', 'Invalid session.', 401)
    return result

def roles(*allowed):
    def dependency(who=Depends(actor)):
        require(who.role in allowed, 'This operation is not permitted for your role.', 'FORBIDDEN_ROLE_OR_CASE', 403)
        return who
    return dependency

def citizen(who=Depends(actor)):
    require(who.kind == 'citizen', 'A citizen session is required.', 'FORBIDDEN_ROLE_OR_CASE', 403)
    return who

def case_access(db, who, case_id, public=False):
    case = db.get(Case, str(case_id))
    if not case: raise DomainError('NOT_FOUND', 'Record not found.', 404)
    allowed = False
    if public:
        allowed = who.kind == 'citizen' and case.citizen_session_id == who.subject
    elif who.role == Role.GOVERNMENT_OFFICER: allowed = True
    elif who.role == Role.INSPECTOR:
        allowed = db.scalar(select(Assignment.id).where(Assignment.case_id == case.id, Assignment.inspector_id == who.subject)) is not None
    require(allowed, 'This operation is not permitted for this record.', 'FORBIDDEN_ROLE_OR_CASE', 403)
    return case

_requests = defaultdict(deque)
def rate_protect(request: Request):
    key = request.client.host if request.client else 'unknown'
    stamp = time.monotonic()
    if len(_requests) > 10000: _requests.clear()
    queue = _requests[key]
    while queue and stamp - queue[0] > 60: queue.popleft()
    if len(queue) >= PROTOTYPE['auth']['rate_limit_per_minute']:
        raise DomainError('RATE_LIMITED', 'Too many requests. Please try again in a minute.', 429, True)
    queue.append(stamp)

