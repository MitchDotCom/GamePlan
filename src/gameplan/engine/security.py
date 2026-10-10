"""Secrets, hashing and throttling for the engine. Everything secret is random, long, shown once, and stored only as an HMAC under a server key."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def new_code(digits: int = 8) -> str:
    return str(secrets.randbelow(10 ** digits)).zfill(digits)


def keyed_hash(secret: str, value: str) -> str:
    """HMAC-SHA256 under the server secret. Tokens are high entropy, but 8-digit codes are not, so a plain hash would fall to a stolen database; the key prevents that."""
    return hmac.new(secret.encode(), value.strip().encode(), hashlib.sha256).hexdigest()


def clean_code(code: str) -> str:
    return "".join(ch for ch in str(code) if ch.isdigit())


class Throttle:
    """Sliding-window limiter per key, in memory (the service is one instance). check() returns False once `limit` calls were made inside `window` seconds."""

    def __init__(self, limit: int, window: float, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key: str) -> bool:
        now = self.clock()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self.lock:
            self.hits.clear()
