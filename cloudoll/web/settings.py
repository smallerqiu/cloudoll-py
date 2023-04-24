import yaml, os


def get_config(env):
    if env is None:
        return {}
    conf_path = os.path.join(os.path.abspath("."), 'config', f'conf.{env}.yaml')
    if not os.path.exists(conf_path):
        return {}
    with open(conf_path) as f:
        config = yaml.safe_load(f)
    return config
