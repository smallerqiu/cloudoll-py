from pathlib import Path
from typing import Any, Optional, Union

import yaml  # type: ignore[import-untyped]
from envyaml import EnvYAML  # type: ignore[import-untyped]

from cloudoll.logging import error, info


def get_config(
    env: Optional[str], root: Optional[Union[str, Path]] = None
) -> dict[str, Any]:
    if env is None:
        return {}
    conf_path = Path(root or Path.cwd()) / "config" / f"conf.{env}.yaml"
    info(f"loading config {conf_path}")
    if not conf_path.exists():
        error(f"Configuration file does not exist: {conf_path}")
        return {}
    with open(conf_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    try:
        config_ori = EnvYAML(conf_path, strict=True)
        config = dict(config_ori)
    except Exception as e:
        error(e)
        raise
    return config or {}
