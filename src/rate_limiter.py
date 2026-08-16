"""Token-bucket rate limiter for GitHub API and LLM calls."""

import time
from dataclasses import dataclass, field


@dataclass
class TokenBucket:
    """Simple token-bucket rate limiter."""
    max_tokens: int
    refill_rate: float  # tokens per second
    tokens: float = 0.0
    last_refill: float = field(default_factory=time.time)
    
    def __post_init__(self):
        self.tokens = float(self.max_tokens)
    
    def _refill(self):
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
    
    def try_acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens. Returns True if allowed, False if rate-limited."""
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    def wait_and_acquire(self, tokens: int = 1) -> float:
        """Wait until tokens are available, then acquire. Returns wait time in seconds."""
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return 0.0
        
        deficit = tokens - self.tokens
        wait_time = deficit / self.refill_rate
        time.sleep(wait_time)
        self._refill()
        self.tokens -= tokens
        return wait_time


class RateLimiter:
    """Rate limiter managing multiple token buckets for different action types.
    
    In production: prevents runaway costs and API bans.
    In prototype: logs when limits would be hit.
    """
    
    def __init__(self, github_per_minute: int = 30, llm_per_minute: int = 20):
        self.buckets = {
            "github": TokenBucket(
                max_tokens=github_per_minute,
                refill_rate=github_per_minute / 60.0,
            ),
            "llm": TokenBucket(
                max_tokens=llm_per_minute,
                refill_rate=llm_per_minute / 60.0,
            ),
        }
    
    def check(self, action_type: str) -> bool:
        """Check if action is allowed without consuming a token."""
        bucket = self.buckets.get(action_type)
        if bucket is None:
            return True
        bucket._refill()
        return bucket.tokens >= 1
    
    def acquire(self, action_type: str) -> bool:
        """Try to acquire a token for the given action type."""
        bucket = self.buckets.get(action_type)
        if bucket is None:
            return True
        return bucket.try_acquire()
    
    def wait_and_acquire(self, action_type: str) -> float:
        """Wait for rate limit and acquire. Returns wait time."""
        bucket = self.buckets.get(action_type)
        if bucket is None:
            return 0.0
        return bucket.wait_and_acquire()
