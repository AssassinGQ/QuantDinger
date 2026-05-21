from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}
_ALLOWED_RANK_TIES = {"average", "first", "dense"}
_ALLOWED_NAN_POLICY = {"drop", "median_fill", "zero_fill"}


@dataclass(frozen=True)
class NormalizeConfig:
    winsor_lower: float = 0.01
    winsor_upper: float = 0.99
    rank_ties: str = "average"
    nan_policy: str = "drop"
    enable_zscore: bool = False
    zscore_ddof: int = 0


def _parse_float(raw: str | None, env_name: str, default: float) -> float:
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{env_name} must be a float, got: {raw!r}") from exc


def _parse_int(raw: str | None, env_name: str, default: int) -> int:
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{env_name} must be an int, got: {raw!r}") from exc


def _parse_bool(raw: str | None, env_name: str, default: bool) -> bool:
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUTHY:
        return True
    if normalized in _FALSY:
        return False
    raise ValueError(f"{env_name} must be one of {_TRUTHY | _FALSY}, got: {raw!r}")


def load_normalize_config_from_env(env: Mapping[str, str] | None = None) -> NormalizeConfig:
    source = env if env is not None else os.environ

    lower = _parse_float(source.get("QD_FACTOR_WINSOR_LOWER"), "QD_FACTOR_WINSOR_LOWER", 0.01)
    upper = _parse_float(source.get("QD_FACTOR_WINSOR_UPPER"), "QD_FACTOR_WINSOR_UPPER", 0.99)
    rank_ties = source.get("QD_FACTOR_RANK_TIES", "average")
    nan_policy = source.get("QD_FACTOR_NAN_POLICY", "drop")
    enable_zscore = _parse_bool(
        source.get("QD_FACTOR_ENABLE_ZSCORE"), "QD_FACTOR_ENABLE_ZSCORE", False
    )
    zscore_ddof = _parse_int(source.get("QD_FACTOR_ZSCORE_DDOF"), "QD_FACTOR_ZSCORE_DDOF", 0)

    if not (0.0 < lower < 1.0):
        raise ValueError(f"QD_FACTOR_WINSOR_LOWER must be in (0, 1), got: {lower}")
    if not (0.0 < upper < 1.0):
        raise ValueError(f"QD_FACTOR_WINSOR_UPPER must be in (0, 1), got: {upper}")
    if upper <= lower:
        raise ValueError("QD_FACTOR_WINSOR_UPPER must be greater than QD_FACTOR_WINSOR_LOWER")
    if rank_ties not in _ALLOWED_RANK_TIES:
        raise ValueError(f"QD_FACTOR_RANK_TIES must be one of {_ALLOWED_RANK_TIES}, got: {rank_ties}")
    if nan_policy not in _ALLOWED_NAN_POLICY:
        raise ValueError(
            f"QD_FACTOR_NAN_POLICY must be one of {_ALLOWED_NAN_POLICY}, got: {nan_policy}"
        )
    if zscore_ddof not in {0, 1}:
        raise ValueError(f"QD_FACTOR_ZSCORE_DDOF must be 0 or 1, got: {zscore_ddof}")

    return NormalizeConfig(
        winsor_lower=lower,
        winsor_upper=upper,
        rank_ties=rank_ties,
        nan_policy=nan_policy,
        enable_zscore=enable_zscore,
        zscore_ddof=zscore_ddof,
    )
