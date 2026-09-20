"""Application-local configuration and path resolution."""

from copy import deepcopy
import math
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
    for section in ("server", "database", "session", "jwt"):
        if section in config and not isinstance(config[section], dict):
            raise ValueError(f"{section} must be a mapping")
    server = config.get("server", {})
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


class Configuration:
    def __init__(self, root: Optional[Union[str, Path]] = None) -> None:
        self.root = Path(root or Path.cwd()).resolve()

    def load(
        self, env: Optional[str], values: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        config = get_config(env, root=self.root) if values is None else values
        if not isinstance(config, dict):
            raise TypeError("Application configuration must be a mapping")
        validate_config(config)
        return deepcopy(config)

    def path(self, name: str) -> Path:
        return self.root / name
