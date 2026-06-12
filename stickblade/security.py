"""Security layer for the arena server: rate limiting, spend protection,
queue caps. Zero external dependencies (in-memory sliding windows) — right-
sized for a free-tier single-instance deployment.

All knobs are env vars (defaults in parentheses):
    RL_MATCHES_PER_HOUR   (50)   matches one IP may start per hour
    RL_VOTES_PER_HOUR     (100)  votes one IP may cast per hour
    RL_REQS_PER_MIN       (120)  any API requests per IP per minute
    MAX_QUEUE             (10)   pending sims before new matches are rejected
    MAX_MATCHES_PER_DAY   (300)  global daily cap (LLM spend ceiling)
    ALLOW_PAID_CUSTOM     (0)    1 = custom model ids may be paid models;
                                 default only ':free' / 'mock:' customs allowed
"""
import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


def _int_env(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


RL_MATCHES_PER_HOUR = _int_env("RL_MATCHES_PER_HOUR", 50)
RL_VOTES_PER_HOUR = _int_env("RL_VOTES_PER_HOUR", 100)
RL_REQS_PER_MIN = _int_env("RL_REQS_PER_MIN", 120)
MAX_QUEUE = _int_env("MAX_QUEUE", 10)
MAX_MATCHES_PER_DAY = _int_env("MAX_MATCHES_PER_DAY", 300)
ALLOW_PAID_CUSTOM = os.environ.get("ALLOW_PAID_CUSTOM", "0") == "1"
# Owner bypass: set ADMIN_TOKEN env var, send X-Admin-Token header to skip
# all rate limits (for testing your own arena without burning the budget).
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")


class SlidingWindow:
    """Per-key sliding-window counter. Memory-bounded by periodic pruning."""

    def __init__(self, limit, window_s):
        self.limit = limit
        self.window = window_s
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()
        self._last_prune = time.time()

    def allow(self, key):
        now = time.time()
        with self.lock:
            q = self.hits[key]
            while q and q[0] <= now - self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False, int(q[0] + self.window - now) + 1
            q.append(now)
            if now - self._last_prune > 600:        # prune dead IPs
                self._last_prune = now
                for k in [k for k, v in self.hits.items() if not v]:
                    del self.hits[k]
            return True, 0


_match_rl = SlidingWindow(RL_MATCHES_PER_HOUR, 3600)
_vote_rl = SlidingWindow(RL_VOTES_PER_HOUR, 3600)
_req_rl = SlidingWindow(RL_REQS_PER_MIN, 60)
_daily_rl = SlidingWindow(MAX_MATCHES_PER_DAY, 86400)


def is_admin(request: Request) -> bool:
    return bool(ADMIN_TOKEN) and \
        request.headers.get("x-admin-token", "") == ADMIN_TOKEN


def client_ip(request: Request) -> str:
    """Real client IP behind HF Spaces / Render / Vercel proxies."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_request(request: Request):
    if is_admin(request):
        return
    ok, retry = _req_rl.allow(client_ip(request))
    if not ok:
        raise HTTPException(429, f"too many requests; retry in {retry}s")


def check_match_allowed(request: Request, queue_size: int):
    if is_admin(request):
        if queue_size >= MAX_QUEUE:
            raise HTTPException(503, "arena is busy — try again in a minute")
        return
    ip = client_ip(request)
    if queue_size >= MAX_QUEUE:
        raise HTTPException(503, "arena is busy — try again in a minute")
    ok, retry = _daily_rl.allow("__global__")
    if not ok:
        raise HTTPException(429, "daily match budget reached — back tomorrow")
    ok, retry = _match_rl.allow(ip)
    if not ok:
        raise HTTPException(
            429, f"match limit reached ({RL_MATCHES_PER_HOUR}/hour); "
                 f"retry in {retry}s")


def check_vote_allowed(request: Request):
    if is_admin(request):
        return
    ok, retry = _vote_rl.allow(client_ip(request))
    if not ok:
        raise HTTPException(429, f"vote limit reached; retry in {retry}s")


def check_model_spend_policy(model_id: str, roster: dict):
    """Custom (non-roster) ids may only be free models unless explicitly
    allowed — stops strangers from burning credits on expensive models."""
    if model_id in roster or model_id.startswith("mock:"):
        return
    if ALLOW_PAID_CUSTOM:
        return
    if not model_id.endswith(":free"):
        raise HTTPException(
            400, "custom models must end in ':free' "
                 "(set ALLOW_PAID_CUSTOM=1 server-side to lift this)")


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
}
