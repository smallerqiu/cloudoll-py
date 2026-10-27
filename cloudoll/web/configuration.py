"""Application-local configuration and path resolution."""

from copy import deepcopy
import math
import ssl
from pathlib import Path
from typing import Any, Optional, Union

from cloudoll.web.settings import get_config
from cloudoll.web.jwt import validate_policy


def parse_int(value: object) -> Optional[int]:
    if isinstance(value, bool):
        raise TypeError("Expected an integer, not a boolean")
    if value is None or isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value.strip())
    raise TypeError("Expected an integer or numeric string")


def validate_config(config: dict[str, Any]) -> None:
    """Validate library-owned fields only; application/plugin keys remain free."""
    for section in ("server", "database", "session", "jwt", "orm"):
        if section in config and not isinstance(config[section], dict):
            raise ValueError(f"{section} must be a mapping")
    orm = config.get("orm", {})
    if set(orm) - {"default"}:
        raise ValueError("Unknown orm option; supported options: default")
    if "default" in orm:
        default = orm["default"]
        if not isinstance(default, str) or not default.strip():
            raise ValueError("orm.default must be a non-empty datasource name")
        if default not in config.get("database", {}):
            raise ValueError(
                f"orm.default references an unknown datasource: {default!r}"
            )
    server = config.get("server", {})
    for key in ("ssl_certfile", "ssl_keyfile"):
        if key in server:
            value = server[key]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"server.{key} must be a non-empty path")
    certfile, keyfile = server.get("ssl_certfile"), server.get("ssl_keyfile")
    if (certfile is None) != (keyfile is None):
        raise ValueError(
            "server.ssl_certfile and server.ssl_keyfile must be set together"
        )
    if "ssl_context" in server and not isinstance(
        server["ssl_context"], ssl.SSLContext
    ):
        raise ValueError("server.ssl_context must be an ssl.SSLContext")
    if "ssl_context" in server and (certfile is not None or keyfile is not None):
        raise ValueError("Use either server.ssl_context or certificate/key paths")
    for key in ("resource_close_timeout", "resource_shutdown_timeout"):
        if key in server:
            value = server[key]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"server.{key} must be a finite positive number")
    for key, low, high in (("port", 1, 65535), ("client_max_size", 0, None)):
        if key in server:
            value = parse_int(server[key])
            if value is None or value < low or (high is not None and value > high):
                raise ValueError(f"Invalid server.{key}")
    if "json_errors" in server and not isinstance(server["json_errors"], bool):
        raise ValueError("server.json_errors must be a boolean")
    for name, database in config.get("database", {}).items():
        if not isinstance(database, dict):
            raise ValueError(f"database.{name} must be a mapping")
    for key in ("secure", "httponly"):
        if key in config.get("session", {}) and not isinstance(
            config["session"][key], bool
        ):
            raise ValueError(f"session.{key} must be a boolean")
    session = config.get("session", {})
    for key in ("key", "domain", "path"):
        if key in session and (not isinstance(session[key], str) or not session[key]):
            raise ValueError(f"session.{key} must be a non-empty string")
    if "samesite" in session:
        same_site = session["samesite"]
        if not isinstance(same_site, str) or same_site.lower() not in {
            "strict",
            "lax",
            "none",
        }:
            raise ValueError("session.samesite must be Strict, Lax or None")
    jwt_config = config.get("jwt", {})
    validate_policy(
        **{
            key: jwt_config[key]
            for key in ("issuer", "audience", "leeway", "require")
            if key in jwt_config
        }
    )
    if "key" in jwt_config and (
        not isinstance(jwt_config["key"], (str, bytes)) or not jwt_config["key"]
    ):
        raise ValueError("jwt.key must be a non-empty string or bytes")
    if "exp" in jwt_config:
        expiry = parse_int(jwt_config["exp"])
        if expiry is None or expiry <= 0:
            raise ValueError("jwt.exp must be a positive integer")


def resolve_root(root: Optional[Union[str, Path]] = None) -> Path:
    return Path(root or Path.cwd()).resolve()


def build_ssl_context(
    server: dict[str, Any], root: Optional[Union[str, Path]] = None
) -> Optional[ssl.SSLContext]:
    """Turn the server TLS options into a context, or None for plain HTTP.

    Relative certificate paths follow the application root, the same rule as
    `Configuration.path()`: a service started from a different working
    directory must still find the files the developer configured.
    """
    base = resolve_root(root)
    supplied = server.get("ssl_context")
    if supplied is not None:
        if not isinstance(supplied, ssl.SSLContext):
            raise ValueError("server.ssl_context must be an ssl.SSLContext")
        if (
            server.get("ssl_certfile") is not None
            or server.get("ssl_keyfile") is not None
        ):
            raise ValueError("Use either server.ssl_context or certificate/key paths")
        return supplied
    certfile, keyfile = server.get("ssl_certfile"), server.get("ssl_keyfile")
    if certfile is None and keyfile is None:
        return None
    if certfile is None or keyfile is None:
        raise ValueError(
            "server.ssl_certfile and server.ssl_keyfile must be set together"
        )

    def located(value: Any, key: str) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"server.{key} must be a non-empty path")
        path = Path(value).expanduser()
        resolved = path if path.is_absolute() else base / path
        if not resolved.is_file():
            raise ValueError(f"server.{key} names a missing file: {resolved}")
        return resolved

    cert_path = located(certfile, "ssl_certfile")
    key_path = located(keyfile, "ssl_keyfile")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        context.load_cert_chain(str(cert_path), str(key_path))
    except (ssl.SSLError, OSError) as exc:
        # The files exist, so the usual cause is a key that does not match the
        # certificate or a format OpenSSL cannot read; name both paths.
        raise ValueError(
            f"server.ssl_certfile {cert_path!s} and server.ssl_keyfile "
            f"{key_path!s} could not be loaded: {exc}"
        ) from exc
    return context


class Configuration:
    def __init__(self, root: Optional[Union[str, Path]] = None) -> None:
        self.root = resolve_root(root)

    def load(
        self, env: Optional[str], values: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        config = get_config(env, root=self.root) if values is None else values
        if not isinstance(config, dict):
            raise TypeError("Application configuration must be a mapping")
        validate_config(config)
        ssl_context = config.get("server", {}).get("ssl_context")
        memo = {id(ssl_context): ssl_context} if ssl_context is not None else None
        return deepcopy(config, memo)

    def path(self, name: str) -> Path:
        return self.root / name
