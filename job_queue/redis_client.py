import os
import time
import logging
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger("orchestra_redis_client")

class MockRedis:
    """
    Thread-safe mock implementation of key Redis operations
    to facilitate database-less offline unit testing.
    """
    _lists: Dict[str, list] = {}
    _hashes: Dict[str, Dict[str, str]] = {}
    _lock = threading.Lock()

    def __init__(self, *args, **kwargs):
        pass

    def ping(self) -> bool:
        return True

    def rpush(self, name: str, *values: str) -> int:
        with self._lock:
            if name not in self._lists:
                self._lists[name] = []
            for val in values:
                self._lists[name].append(val)
            return len(self._lists[name])

    def blpop(self, keys: Any, timeout: int = 0) -> Optional[tuple]:
        if isinstance(keys, str):
            keys = [keys]
        start_time = time.time()
        while True:
            with self._lock:
                for key in keys:
                    if key in self._lists and len(self._lists[key]) > 0:
                        val = self._lists[key].pop(0)
                        return (key, val)
            if timeout > 0 and (time.time() - start_time) >= timeout:
                return None
            time.sleep(0.02)

    def lpop(self, key: str) -> Optional[str]:
        with self._lock:
            if key in self._lists and len(self._lists[key]) > 0:
                return self._lists[key].pop(0)
            return None

    def llen(self, name: str) -> int:
        with self._lock:
            return len(self._lists.get(name, []))

    def hset(self, name: str, key: str, value: str) -> int:
        with self._lock:
            if name not in self._hashes:
                self._hashes[name] = {}
            self._hashes[name][key] = value
            return 1

    def hget(self, name: str, key: str) -> Optional[str]:
        with self._lock:
            if name in self._hashes and key in self._hashes[name]:
                return self._hashes[name][key]
            return None

    def hgetall(self, name: str) -> Dict[str, str]:
        with self._lock:
            return self._hashes.get(name, {}).copy()

    def delete(self, *names: str) -> int:
        with self._lock:
            count = 0
            for name in names:
                if name in self._lists:
                    del self._lists[name]
                    count += 1
                if name in self._hashes:
                    del self._hashes[name]
                    count += 1
            return count


class RedisClient:
    """
    Production-ready wrapper for Redis interactions.
    Automatically drops back to an in-memory thread-safe MockRedis
    if live Redis connection fails or if testing mode is active.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(RedisClient, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self.redis_url = os.environ.get("ORCHESTRA_REDIS_URL", "redis://localhost:6379/0")
        self.test_mode = os.environ.get("ORCHESTRA_TEST_MODE", "false").lower() == "true"
        self._client = None
        self._init_connection()
        self._initialized = True

    def _init_connection(self):
        if self.test_mode:
            logger.info("Initializing mock in-memory Redis client (Testing Mode)")
            self._client = MockRedis()
            return

        try:
            import redis
            logger.info(f"Connecting to Redis at {self.redis_url}")
            client = redis.Redis.from_url(self.redis_url, decode_responses=True)
            client.ping()
            self._client = client
            logger.info("Successfully connected to live Redis service")
        except Exception as e:
            logger.warning(
                f"Failed to connect to live Redis ({e}). Falling back to in-memory MockRedis."
            )
            self._client = MockRedis()

    @property
    def client(self):
        return self._client
