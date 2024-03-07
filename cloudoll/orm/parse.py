from urllib.parse import unquote
import re
from typing import Any, Optional, List, cast
import collections.abc as collections_abc

_implicit_encoding = "ascii"
_implicit_errors = "strict"

__ALL__ = "parse_coon"


def parse_coon(url: str):
    pattern = re.compile(
        r"""
            (?P<type>[\w\+]+)://
            (?:
                (?P<username>[^:/]*)
                (?::(?P<password>[^@]*))?
            @)?
            (?:
                (?:
                    \[(?P<ipv6host>[^/\?]+)\] |
                    (?P<ipv4host>[^/:\?]+)
                )?
                (?::(?P<port>[^/\?]*))?
            )?
            (?:/(?P<db>[^\?]*))?
            (?:\?(?P<query>.*))?
            """,
        re.X,
    )
    match = pattern.match(url)
    if match is not None:
        configs = match.groupdict()
        if configs["username"] is not None:
            configs["username"] = unquote(configs["username"])

        if configs["password"] is not None:
            configs["password"] = unquote(configs["password"])

        ipv4host = configs.pop("ipv4host")
        ipv6host = configs.pop("ipv6host")
        configs["host"] = ipv4host or ipv6host
        # name = components.pop("name")

        if configs["port"]:
            configs["port"] = int(configs["port"])

        query = {}
        if configs["query"] is not None:

            for key, value in parse_qsl(configs["query"]):
                if key in query:
                    query[key] = to_list(query[key])
                    cast("List[str]", query[key]).append(value)
                else:
                    query[key] = value

        return configs, query
    else:
        raise ValueError("%s is not a valid database URL" % url)


def to_list(x: Any, default: Optional[List[Any]] = None) -> List[Any]:
    if x is None:
        return default  # type: ignore
    if not isinstance(x, collections_abc.Iterable) or isinstance(x, (str, bytes)):
        return [x]
    elif isinstance(x, list):
        return x
    else:
        return list(x)


def parse_qsl(
    qs,
    keep_blank_values=False,
    strict_parsing=False,
    encoding="utf-8",
    errors="replace",
    max_num_fields=None,
    separator="&",
):
    qs, _coerce_result = _coerce_args(qs)
    separator, _ = _coerce_args(separator)

    if not separator or (not isinstance(separator, (str, bytes))):
        raise ValueError("Separator must be of type string or bytes.")

    if max_num_fields is not None:
        num_fields = 1 + qs.count(separator) if qs else 0
        if max_num_fields < num_fields:
            raise ValueError("Max number of fields exceeded")

    r = []
    query_args = qs.split(separator) if qs else []
    for name_value in query_args:
        if not name_value and not strict_parsing:
            continue
        nv = name_value.split("=", 1)
        if len(nv) != 2:
            if strict_parsing:
                raise ValueError("bad query field: %r" % (name_value,))
            # Handle case of a control-name with no equal sign
            if keep_blank_values:
                nv.append("")
            else:
                continue
        if len(nv[1]) or keep_blank_values:
            name = nv[0].replace("+", " ")
            name = unquote(name, encoding=encoding, errors=errors)
            name = _coerce_result(name)
            value = nv[1].replace("+", " ")
            value = unquote(value, encoding=encoding, errors=errors)
            value = _coerce_result(value)
            r.append((name, value))
    return r


def _encode_result(obj, encoding=_implicit_encoding, errors=_implicit_errors):
    return obj.encode(encoding, errors)


def _noop(obj):
    return obj


def _decode_args(args, encoding=_implicit_encoding, errors=_implicit_errors):
    return tuple(x.decode(encoding, errors) if x else "" for x in args)


def _coerce_args(*args):
    str_input = isinstance(args[0], str)
    for arg in args[1:]:
        if arg and isinstance(arg, str) != str_input:
            raise TypeError("Cannot mix str and non-str arguments")
    if str_input:
        return args + (_noop,)
    return _decode_args(args) + (_encode_result,)
