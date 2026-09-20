"""Session storage configuration; one manager per application."""
import hashlib
import os
import secrets
from urllib import parse
from aiohttp_session import cookie_storage, setup
from cloudoll.logging import info, warning
from cloudoll.web.configuration import parse_int


class SessionManager:
    def __init__(self, owner):
        self.owner = owner
        self.secret = None

    async def start(self, apps):
        config = self.owner.config or {}
        sess = config.get("session", {})

        max_age = sess.get("max_age")
        httponly = sess.get("httponly", True)
        cookie_name = sess.get("key", "CLOUDOLL_SESSION")
        secure = sess.get("secure", False)

        # redis
        redis_conf = sess.get("redis")
        if isinstance(redis_conf, str):
            redis_conf = {"url": redis_conf}
        mcache_conf = sess.get("memcached")

        if redis_conf:
            from aiohttp_session import redis_storage
            redis_url = redis_conf.get("url")
            qs = {}
            if not redis_url:
                redis_type = redis_conf.get("type", "redis")
                username = redis_conf.get("username")
                password = redis_conf.get("password")
                auth = ""
                if username is not None:
                    auth = f"{parse.quote(str(username), safe='')}:{parse.quote(str(password or ''), safe='')}@"
                elif password is not None:
                    auth = f":{parse.quote(str(password), safe='')}@"
                host = redis_conf.get("host", "localhost")
                port = redis_conf.get("port", 6379)
                db = redis_conf.get("db", 0)
                redis_url = f"{redis_type}://{auth}{host}:{port}/{db}"

            from redis import asyncio as aioredis

            redis = await aioredis.from_url(redis_url, **qs)
            apps.redis = redis
            storage = redis_storage.RedisStorage(
                redis,
                cookie_name=cookie_name,
                max_age=parse_int(max_age),
                httponly=httponly,
                secure=secure,
            )
            setup(apps, storage)
            info("starting a redis session.")
        elif mcache_conf:
            from aiohttp_session import memcached_storage
            host = mcache_conf.get("host")
            port = mcache_conf.get("port", 11211)

            import aiomcache

            mc = aiomcache.Client(host, port)
            apps.memcached = mc
            storage = memcached_storage.MemcachedStorage(
                mc,
                cookie_name=cookie_name,
                max_age=parse_int(max_age),
                httponly=httponly,
                secure=secure,
            )
            setup(apps, storage)
            info("starting a memcached session.")
        else:
            configured_secret = sess.get("secret_key") or os.getenv(
                "CLOUDOLL_SESSION_SECRET"
            )
            if configured_secret:
                secret_key = hashlib.sha256(str(configured_secret).encode()).digest()
            else:
                if self.secret is None:
                    self.secret = secrets.token_bytes(32)
                    warning(
                        "No session secret configured; using a random process-local key. "
                        "Set session.secret_key or CLOUDOLL_SESSION_SECRET in production."
                    )
                secret_key = self.secret

            storage = cookie_storage.EncryptedCookieStorage(
                secret_key,
                cookie_name=cookie_name,
                max_age=parse_int(max_age),
                httponly=httponly,
                secure=secure,
            )
            setup(apps, storage)
            info("starting local cookie.")
