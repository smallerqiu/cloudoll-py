class Object(dict):
    __setattr__ = dict.__setitem__
    __getattr__ = dict.__getitem__


def chainMap(*dicts):
    merged_dict = Object()
    for d in dicts:
        for key, value in d.items():
            if key not in merged_dict or value is not None:
                merged_dict[key] = value
    return merged_dict
