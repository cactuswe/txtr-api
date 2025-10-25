import re
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple, TypeVar

T = TypeVar('T')

class RateLimitError(Exception):
    """Raised when rate limit is exceeded."""
    pass


class SimpleTTLCache:
    """Thread-safe in-memory TTL cache."""
    
    def __init__(self) -> None:
        self._cache: Dict[str, Tuple[datetime, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """Get value if exists and not expired. Also cleans expired entries."""
        now = datetime.now()
        
        with self._lock:
            # Clean expired entries
            expired_keys = [
                k for k, (expires_at, _) in self._cache.items()
                if expires_at < now
            ]
            for k in expired_keys:
                del self._cache[k]
            
            # Return requested value if valid
            if key not in self._cache:
                return None
            
            expires_at, value = self._cache[key]
            if expires_at < now:
                del self._cache[key]
                return None
                
            return value

    def set(self, key: str, value: Any, ttl_s: int) -> None:
        """Set value with TTL in seconds."""
        with self._lock:
            expires_at = datetime.now() + timedelta(seconds=ttl_s)
            self._cache[key] = (expires_at, value)

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()


class RateLimiter:
    """Thread-safe rate limiter using token bucket algorithm."""
    
    def __init__(self) -> None:
        self._buckets: Dict[str, Dict[str, float]] = {}  # ip -> {tokens, ts}
        self._lock = threading.Lock()
        self.RATE = 60    # tokens per minute
        self.BURST = 30   # max tokens
        
    def check_rate_limit(self, ip: str, limit_per_min: int) -> None:
        """Check if rate limit is exceeded for IP."""
        now = time.time()
        
        with self._lock:
            b = self._buckets.get(ip, {"tokens": self.BURST, "ts": now})
            
            # Refill tokens based on elapsed time
            b["tokens"] = min(
                self.BURST,
                b["tokens"] + self.RATE * (now - b["ts"]) / 60.0
            )
            b["ts"] = now
            
            # Check if request can be allowed
            if b["tokens"] < 1:
                self._buckets[ip] = b
                raise RateLimitError("Rate limit exceeded")
            
            # Consume one token
            b["tokens"] -= 1
            self._buckets[ip] = b


def get_request_id() -> str:
    """Generate a unique request ID."""
    return str(uuid.uuid4())


def normalize_text(text: str) -> str:
    """Normalize text by trimming and collapsing whitespace."""
    if not text:
        return ""
    return " ".join(text.split())


def word_count(text: str) -> int:
    """Count words in text using regex."""
    if not text:
        return 0
    words = re.findall(r'\w+', text)
    return len(words)


def first_sentences(text: str, n: int) -> str:
    """Return first n sentences from text."""
    if not text or n <= 0:
        return ""
    
    # Split on sentence endings followed by space
    sentences = re.split(r'[.!?]\s+', text.strip())
    selected = sentences[:n]
    
    # Restore sentence endings except for last sentence
    result = '. '.join(selected)
    
    # Add final period if original text ended with one
    if text.rstrip().endswith('.'):
        result += '.'
        
    return result


def elapsed_ms(start: float) -> int:
    """Calculate elapsed milliseconds from start time."""
    return int((time.perf_counter() - start) * 1000)


def validate_url(u: str) -> str:
    """Validate URL format and length."""
    if len(u) > 2048:
        raise ValueError("url too long")
    if not (u.startswith("http://") or u.startswith("https://")):
        raise ValueError("unsupported scheme")
    
    from pydantic import AnyHttpUrl
    _ = AnyHttpUrl(u)  # only for validation
    return str(u)      # return str, not Url object


_CITE_RE = re.compile(r"\s*\[\d+\]\s*")
_SPACE_RE = re.compile(r"\s+")

def clean_citations_and_spaces(s: str) -> str:
    """Clean citations and normalize spaces."""
    if not s:
        return s
    s = _CITE_RE.sub(" ", s)            # remove [12], [a], [b] etc
    s = s.replace(" ,", ",").replace(" .", ".").replace(" ;", ";").replace(" :", ":")
    s = _SPACE_RE.sub(" ", s).strip()
    return s