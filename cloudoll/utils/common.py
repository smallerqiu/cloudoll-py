

def chainMap(*dicts):
    merged_dict = {}
    for d in dicts:
        for key, value in d.items():
            if key not in merged_dict or value is not None:
                merged_dict[key] = value
    return merged_dict
