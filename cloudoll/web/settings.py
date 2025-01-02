import yaml
import os
from ..logging import error, info
from envyaml import EnvYAML


def get_config(env):
    if env is None:
        return {}
    conf_path = os.path.join(os.path.abspath("."), "config", f"conf.{env}.yaml")
    info(f"loading config {conf_path}")
    if not os.path.exists(conf_path):
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
