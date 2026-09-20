"""Application-local configuration and path resolution."""

from copy import deepcopy
from pathlib import Path
from typing import Any, Optional, Union

from cloudoll.web.settings import get_config


def parse_int(value: object) -> Optional[int]:
    if value is None or isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value.strip())
    raise TypeError("Expected an integer or numeric string")


class Configuration:
    def __init__(self, root: Optional[Union[str, Path]] = None) -> None:
        self.root = Path(root or Path.cwd()).resolve()

    def load(
        self, env: Optional[str], values: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        config = get_config(env, root=self.root) if values is None else values
        if not isinstance(config, dict):
            raise TypeError("Application configuration must be a mapping")
        return deepcopy(config)

    def path(self, name: str) -> Path:
        return self.root / name
