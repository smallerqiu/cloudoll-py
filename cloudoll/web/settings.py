from pathlib import Path
import yaml
from cloudoll.logging import error, info
from envyaml import EnvYAML


def get_config(env):
    if env is None:
        return {}
    conf_path = Path().cwd() / "config" / f"conf.{env}.yaml"
    info(f"loading config {conf_path}")
    if not conf_path.exists():
        error(f"Configuration file does not exist: {conf_path}")
        return {}
    with open(conf_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    try:
        config_ori = EnvYAML(conf_path, strict=False)
        config = dict(config_ori)
    except BaseException as e:
        error(e)
    return config or {}
