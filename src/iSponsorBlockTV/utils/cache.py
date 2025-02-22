import datetime

from typing import Any, Callable
from functools import wraps

from cache.key import KEY
from cache.lru import LRU
from cache.async_ttl import AsyncTTL


class AsyncConditionalTTL(AsyncTTL):
    class _TTL(AsyncTTL._TTL):
        def __setitem__(self, key, value):
            # Expecting value to be a tuple: (actual_value, ignore_ttl)
            actual_value, ignore_ttl = value
            ttl_value = (datetime.datetime.now() + self.time_to_live) if (self.time_to_live and not ignore_ttl) else None
            # Bypass AsyncTTL._TTL.__setitem__ to avoid re-applying a TTL.
            LRU.__setitem__(self, key, (actual_value, ttl_value))

    def __init__(self, time_to_live=60, maxsize=1024, skip_args: int = 0):
        """

        :param time_to_live: Use time_to_live as None for non expiring cache
        :param maxsize: Use maxsize as None for unlimited size cache
        :param skip_args: Use `1` to skip first arg of func in determining cache key
        """
        super().__init__(time_to_live, maxsize, skip_args)
        # Override the ttl instance with our customised version.
        self.ttl = self._TTL(time_to_live, maxsize)

    def __call__(self, func):
        async def wrapper(*args, **kwargs):
            key = KEY(args[self.skip_args:], kwargs)
            if key in self.ttl:
                return self.ttl[key]
            else:
                # Here, the wrapped function must return a tuple: (value, ignore_ttl)
                self.ttl[key] = await func(*args, **kwargs)
                return self.ttl[key]
        wrapper.__name__ += func.__name__
        return wrapper

def list_to_tuple(function: Callable) -> Callable:
    @wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        args = [tuple(x) if isinstance(x, list) else x for x in args]
        result = function(*args)
        return tuple(result) if isinstance(result, list) else result

    return wrapper
