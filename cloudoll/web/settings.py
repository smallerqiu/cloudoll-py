import yaml
import os
from ..logging import error, print_info


def get_config(env):
    if env is None:
        return {}
    conf_path = os.path.join(os.path.abspath("."), "config", f"conf.{env}.yaml")
    print_info(f"loading config {conf_path}")
    if not os.path.exists(conf_path):
        error(f"Configuration file does not exist: {conf_path}")
        return {}
    with open(conf_path) as f:
        config = yaml.safe_load(f)
    return config or {}
