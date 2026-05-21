from __future__ import annotations

import pandas as pd

from .factor_defs import compute_factor_by_name


def build_factor_panels(
    price_panel: pd.DataFrame,
    volume_panel: pd.DataFrame | None,
    factor_names: list[str],
) -> dict[str, pd.DataFrame]:
    if volume_panel is None:
        volume_panel = pd.DataFrame(index=price_panel.index, columns=price_panel.columns, dtype=float)
    else:
        volume_panel = volume_panel.reindex(index=price_panel.index, columns=price_panel.columns)

    out: dict[str, pd.DataFrame] = {}
    for factor_name in factor_names:
        cols = {}
        for symbol in price_panel.columns:
            close = price_panel[symbol]
            volume = volume_panel[symbol] if symbol in volume_panel.columns else None
            cols[symbol] = compute_factor_by_name(factor_name, close=close, volume=volume)
        out[factor_name] = pd.DataFrame(cols, index=price_panel.index)
    return out
