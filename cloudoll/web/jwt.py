__author__ = "Qiu / smallerqiu@gmail.com"

import datetime
import math
from collections.abc import Mapping, Sequence
from typing import Any, Optional, Union

import jwt


def encode(
    payload: Mapping[str, Any], key: Union[str, bytes], exp: Union[int, str] = 3600
) -> str:
    """
    Sign a JWT (the payload is not encrypted).
    :params payload
    :params key
    :params exp 过期时间单位秒，默认1个小时
    """
    headers = dict(typ="jwt", alg="HS256")
    exp_seconds = int(exp.strip()) if isinstance(exp, str) else exp
    if (
        isinstance(exp_seconds, bool)
        or not isinstance(exp_seconds, int)
        or exp_seconds <= 0
    ):
        raise ValueError("exp must be a positive number of seconds")
    exp_datetime = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        seconds=exp_seconds
    )  # 过期时间
    payload = dict(payload, exp=int(exp_datetime.timestamp()))
    result = jwt.encode(payload=payload, key=key, algorithm="HS256", headers=headers)
    return result


def decode(
    token: Union[str, bytes],
    key: Union[str, bytes],
    *,
    issuer: Optional[str] = None,
    audience: Optional[Union[str, Sequence[str]]] = None,
    leeway: float = 0,
    require: Sequence[str] = ("exp",),
) -> Optional[dict[str, Any]]:
    """Verify HS256 tokens; invalid credentials return None, bad config raises.

    Expiry is required by default. Explicit ``require=()`` permits legacy tokens.
    No credential contents are logged by this helper.
    """
    validate_policy(issuer=issuer, audience=audience, leeway=leeway, require=require)
    if not isinstance(key, (str, bytes)) or not key:
        raise ValueError("JWT key must be a non-empty string or bytes")
    try:
        required = list(require)
        if issuer is not None:
            required.append("iss")
        if audience is not None:
            required.append("aud")
        payload: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=["HS256"],
            issuer=issuer,
            audience=audience,
            leeway=leeway,
            options={"require": required},
        )
        return payload
    except jwt.InvalidTokenError:
        return None


def validate_policy(
    *,
    issuer: Optional[str] = None,
    audience: Optional[Union[str, Sequence[str]]] = None,
    leeway: float = 0,
    require: Sequence[str] = ("exp",),
) -> None:
    if issuer is not None and (not isinstance(issuer, str) or not issuer):
        raise ValueError("JWT issuer must be a non-empty string")
    if audience is not None:
        audiences = [audience] if isinstance(audience, str) else audience
        if (
            not isinstance(audiences, (list, tuple))
            or not audiences
            or any(not isinstance(item, str) or not item for item in audiences)
        ):
            raise ValueError(
                "JWT audience must be a string or a non-empty list of strings"
            )
    if (
        isinstance(leeway, bool)
        or not isinstance(leeway, (int, float))
        or not math.isfinite(leeway)
        or leeway < 0
    ):
        raise ValueError("JWT leeway must be a finite non-negative number")
    if not isinstance(require, (list, tuple)) or any(
        not isinstance(item, str) or not item for item in require
    ):
        raise ValueError("JWT require must be a list or tuple of claim names")
