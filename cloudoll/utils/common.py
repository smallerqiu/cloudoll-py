class Object(dict):
    def __init__(self, obj: dict = {}):
        super().__init__()
        for k, v in obj.items():
            self[k] = v

    def __getattr__(self, key):
        return self[key] if key in self else ""

    def __setattr__(self, key, value):
        self[key] = value

    def __str__(self):
        return self.key


def chainMap(*dicts):
    merged_dict = Object()
    for d in dicts:
        for key, value in d.items():
            if key not in merged_dict or value is not None:
                merged_dict[key] = value
    return merged_dict
