"""
Memoization Utilities - Infrastructure Layer

Provides memoization decorators and utilities for caching expensive computations.
"""

import functools
import time
import hashlib
import json
from typing import Any, Callable, Dict, Optional, Tuple, Union
from collections import OrderedDict
import asyncio
import re


class LRUCache:
    """Thread-safe LRU cache implementation."""

    def __init__(self, maxsize: int = 128):
        self.cache = OrderedDict()
        self.maxsize = maxsize
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        async with self._lock:
            if key in self.cache:
                # Move to end (most recently used)
                self.cache.move_to_end(key)
                return self.cache[key]
            return None

    async def set(self, key: str, value: Any) -> None:
        """Set value in cache."""
        async with self._lock:
            if key in self.cache:
                # Update existing
                self.cache.move_to_end(key)
            self.cache[key] = value

            # Remove oldest if over capacity
            if len(self.cache) > self.maxsize:
                self.cache.popitem(last=False)


class TTLCache:
    """Time-based cache with TTL support."""

    def __init__(self, ttl_seconds: int = 300):
        self.cache: Dict[str, Tuple[Any, float]] = {}
        self.ttl = ttl_seconds
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        async with self._lock:
            if key in self.cache:
                value, timestamp = self.cache[key]
                if time.time() - timestamp < self.ttl:
                    return value
                else:
                    # Expired, remove it
                    del self.cache[key]
            return None

    async def set(self, key: str, value: Any) -> None:
        """Set value in cache with timestamp."""
        async with self._lock:
            self.cache[key] = (value, time.time())


def memoize(maxsize: int = 128, ttl: Optional[int] = None):
    """
    Decorator for memoizing function results.

    Args:
        maxsize: Maximum number of cached results
        ttl: Time-to-live in seconds (None for no expiration)
    """

    def decorator(func: Callable) -> Callable:
        # Use TTL cache if TTL specified, otherwise LRU
        cache = TTLCache(ttl) if ttl else LRUCache(maxsize)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Create cache key from arguments
            key = _make_cache_key(func.__name__, args, kwargs)

            # Check cache
            result = await cache.get(key)
            if result is not None:
                return result

            # Compute result
            result = await func(*args, **kwargs)

            # Store in cache
            await cache.set(key, result)

            return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Create cache key from arguments
            key = _make_cache_key(func.__name__, args, kwargs)

            # For sync functions, use a simple dict cache
            if not hasattr(func, "_cache"):
                func._cache = {}

            if key in func._cache:
                return func._cache[key]

            # Compute result
            result = func(*args, **kwargs)

            # Store in cache
            func._cache[key] = result

            # Limit cache size for sync version
            if len(func._cache) > maxsize:
                # Remove oldest entry
                oldest = next(iter(func._cache))
                del func._cache[oldest]

            return result

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def memoize_method(maxsize: int = 128, ttl: Optional[int] = None):
    """
    Decorator for memoizing instance method results.
    Includes instance in cache key.
    """

    def decorator(method: Callable) -> Callable:
        method_name = method.__name__
        cache_attr = f"_memoize_cache_{method_name}"

        @functools.wraps(method)
        def wrapper(self, *args, **kwargs):
            # Get or create cache for this instance
            if not hasattr(self, cache_attr):
                setattr(self, cache_attr, {})
            cache = getattr(self, cache_attr)

            # Create cache key
            key = _make_cache_key(method_name, args, kwargs)

            # Check cache
            if ttl:
                if key in cache:
                    value, timestamp = cache[key]
                    if time.time() - timestamp < ttl:
                        return value
            else:
                if key in cache:
                    return cache[key]

            # Compute result
            result = method(self, *args, **kwargs)

            # Store in cache
            if ttl:
                cache[key] = (result, time.time())
            else:
                cache[key] = result

            # Limit cache size
            if len(cache) > maxsize:
                oldest = next(iter(cache))
                del cache[oldest]

            return result

        return wrapper

    return decorator


def _make_cache_key(func_name: str, args: Tuple, kwargs: Dict) -> str:
    """Create a cache key from function name and arguments."""
    # Convert args and kwargs to a hashable representation
    key_parts = [func_name]

    # Add args
    for arg in args:
        if isinstance(arg, (str, int, float, bool, type(None))):
            key_parts.append(str(arg))
        elif isinstance(arg, (list, tuple)):
            key_parts.append(json.dumps(arg, sort_keys=True))
        elif isinstance(arg, dict):
            key_parts.append(json.dumps(arg, sort_keys=True))
        else:
            # For complex objects, use their string representation
            key_parts.append(str(arg))

    # Add kwargs
    if kwargs:
        key_parts.append(json.dumps(kwargs, sort_keys=True))

    # Create hash of the key
    key_str = "|".join(key_parts)
    return hashlib.md5(key_str.encode()).hexdigest()


class RegexCache:
    """Cache for compiled regex patterns."""

    def __init__(self, maxsize: int = 100):
        self._cache: Dict[str, re.Pattern] = {}
        self._maxsize = maxsize

    def get_pattern(self, pattern: str, flags: int = 0) -> re.Pattern:
        """Get compiled regex pattern from cache."""
        key = f"{pattern}:{flags}"

        if key not in self._cache:
            # Compile and cache
            self._cache[key] = re.compile(pattern, flags)

            # Limit cache size
            if len(self._cache) > self._maxsize:
                # Remove oldest
                oldest = next(iter(self._cache))
                del self._cache[oldest]

        return self._cache[key]


# Global regex cache instance
regex_cache = RegexCache()


def cached_property(func: Callable) -> property:
    """
    Decorator that converts a method into a cached property.
    The value is computed on first access and cached.
    """
    attr_name = f"_cached_{func.__name__}"

    @functools.wraps(func)
    def wrapper(self):
        if not hasattr(self, attr_name):
            setattr(self, attr_name, func(self))
        return getattr(self, attr_name)

    return property(wrapper)


class MemoizationStats:
    """Track memoization statistics for monitoring."""

    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def record_hit(self):
        """Record a cache hit."""
        self.hits += 1

    def record_miss(self):
        """Record a cache miss."""
        self.misses += 1

    def record_eviction(self):
        """Record a cache eviction."""
        self.evictions += 1

    def reset(self):
        """Reset statistics."""
        self.hits = 0
        self.misses = 0
        self.evictions = 0
