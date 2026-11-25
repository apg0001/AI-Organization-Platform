"""로컬 계정 인증.

- 비밀번호: scrypt(n=2^14, r=8, p=1, 32바이트, 무작위 16바이트 솔트). 형식 `scrypt$n$r$p$salt$hash`(base64).
- 세션: 무작위 토큰(32바이트)을 HttpOnly 쿠키로 주고, DB에는 SHA-256 해시만 저장.
  30일, 하루 이상 지나면 만료 연장.
- 로그인 시도 제한: 아이디별 연속 실패 5회부터 2^(n-5)초(최대 5분) 대기.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ai_org.models import AuthSession, User

COOKIE = "ai_org_session"
SESSION_TTL = timedelta(days=30)
SLIDE_AFTER = timedelta(days=1)
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
MIN_PASSWORD = 8


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    b64 = base64.b64encode
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${b64(salt).decode()}${b64(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, base64.b64decode(digest))


# 없는 아이디도 같은 비용으로 검증하기 위한 해시(로그인 응답 시간으로 아이디 존재가 드러나지 않게).
DUMMY_HASH = hash_password(secrets.token_hex(16))


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def now() -> datetime:
    return datetime.now(UTC)


def has_users(db: Session) -> bool:
    return db.scalar(select(User.id).limit(1)) is not None


def create_session(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(user_id=user.id, token_hash=token_hash(token), expires_at=now() + SESSION_TTL))
    user.last_login_at = now()
    db.commit()
    return token


def user_for_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    record = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash(token)))
    if record is None:
        return None
    current = now()
    if record.expires_at <= current:
        db.delete(record)
        db.commit()
        return None
    if current - record.last_seen_at > SLIDE_AFTER:
        record.last_seen_at, record.expires_at = current, current + SESSION_TTL
        db.commit()
    return db.get(User, record.user_id)


def end_session(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(token)))
        db.commit()


def end_other_sessions(db: Session, user_id: str, keep_token: str | None) -> None:
    keep = token_hash(keep_token) if keep_token else ""
    db.execute(delete(AuthSession).where(AuthSession.user_id == user_id, AuthSession.token_hash != keep))
    db.commit()


class LoginThrottle:
    """아이디별 연속 실패에 따른 대기(프로세스 메모리)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures: dict[str, tuple[int, float]] = {}

    def wait_seconds(self, key: str) -> float:
        with self._lock:
            _count, until = self._failures.get(key, (0, 0.0))
        return max(0.0, until - time.monotonic())

    def failed(self, key: str) -> None:
        with self._lock:
            count, _ = self._failures.get(key, (0, 0.0))
            count += 1
            delay = 0.0 if count < 5 else min(300.0, 2.0 ** (count - 5))
            self._failures[key] = (count, time.monotonic() + delay)

    def succeeded(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
