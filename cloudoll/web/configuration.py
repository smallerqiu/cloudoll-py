"""Application-local configuration and path resolution."""
from copy import deepcopy
from pathlib import Path

from cloudoll.web.settings import get_config


def parse_int(value):
    if value is None or isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value.strip())
    raise TypeError("Expected an integer or numeric string")


class Configuration:
    def __init__(self, root=None):
        self.root = Path(root or Path.cwd()).resolve()

    def load(self, env, values=None):
        config = get_config(env, root=self.root) if values is None else values
        if not isinstance(config, dict):
            raise TypeError("Application configuration must be a mapping")
        return deepcopy(config)

    def path(self, name):
        return self.root / name
