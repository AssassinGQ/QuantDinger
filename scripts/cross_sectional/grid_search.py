#!/usr/bin/env python3
"""
NQ100 Cross-Sectional Grid Search Script (Phase 23)

Search space:
  - Config-driven factor list from YAML
  - All combinations from combo_min to combo_max
  - Multiple holdings options (n_long_options)

Features:
  - YAML config parsing with safe_load
  - Factor combination generation with directions
  - CLI argument parsing
  - Walk-forward validation (Phase 23 Plan 04)
  - Checkpoint resume (Phase 23 Plan 03)
  - JSONL/CSV/HTML output (Phase 23 Plan 02)

Usage:
  python3 grid_search.py --config grid_config.yaml
  python3 grid_search.py --config custom.yaml --base-url http://localhost:5000
"""
import argparse
import json
import os
import sys
import time
import yaml
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from itertools import combinations


# ═══════════════════════════════════════════════════════════════
# Factor Direction Map (from Phase 20 FACTOR_DEFS)
# ═══════════════════════════════════════════════════════════════

FACTOR_DIRECTION_MAP = {
    # Momentum: positive direction (higher = better)
    "MOM_1M": 1,
    "MOM_3M": 1,
    "MOM_6M": 1,
    "MOM_12M_1M": 1,
    # Reversal: negative direction (lower = better)
    "REV_1W": -1,
    "REV_2W": -1,
    "REV_1M": -1,
    # Volatility: negative direction
    "VOL_20D": -1,
    "VOL_60D": -1,
    # Risk-adjusted: positive direction
    "SHARPE_60D": 1,
    "SORTINO_60D": 1,
    # Distance from MA: negative direction
    "DIST_MA50": -1,
    "DIST_MA200": -1,
    # Volume ratio: negative direction
    "VOL_RATIO": -1,
}


# ═══════════════════════════════════════════════════════════════
# Config Loading (T-23-01 mitigation: safe_load only)
# ═══════════════════════════════════════════════════════════════

def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load YAML config file with search space parameters.

    Args:
        config_path: Path to YAML config file

    Returns:
        Dict with search_space, walk_forward, backtest_defaults, output sections

    Raises:
        FileNotFoundError: If config file does not exist
        yaml.YAMLError: If YAML parsing fails
        ValueError: If required fields are missing or invalid
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)  # T-23-01 mitigation: safe_load only

    # Validate required fields per D-02
    if 'search_space' not in config:
        raise ValueError("Config missing required field: search_space")

    ss = config['search_space']
    required = ['factors', 'combo_min', 'combo_max', 'n_long_options']
    for field in required:
        if field not in ss:
            raise ValueError(f"Config missing required field: search_space.{field}")

    # Validate factors is non-empty list
    if not isinstance(ss['factors'], list) or len(ss['factors']) == 0:
        raise ValueError("search_space.factors must be non-empty list")

    # Validate combo ranges
    if ss['combo_min'] < 1 or ss['combo_max'] < ss['combo_min']:
        raise ValueError("Invalid combo_min/combo_max values")

    # Validate n_long_options is non-empty
    if not isinstance(ss['n_long_options'], list) or len(ss['n_long_options']) == 0:
        raise ValueError("search_space.n_long_options must be non-empty list")

    return config


# ═══════════════════════════════════════════════════════════════
# Factor Combination Generation
# ═══════════════════════════════════════════════════════════════

def generate_factor_combinations(
    factors: List[str],
    combo_min: int,
    combo_max: int,
) -> List[Dict[str, Any]]:
    """
    Generate all factor subset combinations from combo_min to combo_max.

    Args:
        factors: List of factor names
        combo_min: Minimum combination size (>= 1)
        combo_max: Maximum combination size (<= len(factors))

    Returns:
        List of dicts with 'factors' (list) and 'directions' (list of +/-1)
    """
    combos = []

    # Clamp combo_max to available factors
    actual_max = min(combo_max, len(factors))

    for size in range(combo_min, actual_max + 1):
        for factor_tuple in combinations(factors, size):
            factor_list = list(factor_tuple)
            # Get direction for each factor (default to 1 if unknown)
            directions = [FACTOR_DIRECTION_MAP.get(f, 1) for f in factor_list]
            combos.append({
                'factors': factor_list,
                'directions': directions,
            })

    return combos


# ═══════════════════════════════════════════════════════════════
# CLI Argument Parsing
# ═══════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    """
    Parse CLI arguments for grid search script.

    Returns:
        argparse.Namespace with config, base_url, auth options, output_dir
    """
    parser = argparse.ArgumentParser(
        description="NQ100 Cross-Sectional Grid Search Script (Phase 23)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Config path per D-03
    parser.add_argument(
        "--config",
        default="grid_config.yaml",
        help="Path to YAML config file",
    )

    # API endpoint
    parser.add_argument(
        "--base-url",
        default="http://localhost:5000",
        help="Backend API base URL",
    )

    # Authentication: token OR username/password
    parser.add_argument(
        "--token",
        default=None,
        help="API authentication token (or use --username/--password)",
    )
    parser.add_argument(
        "--username",
        default="backtest_bot",
        help="Username for API login (if --token not provided)",
    )
    parser.add_argument(
        "--password",
        default="backtest123",
        help="Password for API login (if --token not provided)",
    )

    # Output directory
    parser.add_argument(
        "--output-dir",
        default="results",
        help="Directory for output files (JSONL, CSV, HTML, checkpoint)",
    )

    return parser.parse_args()


# ═══════════════════════════════════════════════════════════════
# Phase 22 HTTP API Integration
# ═══════════════════════════════════════════════════════════════

def login(base_url: str, username: str, password: str) -> str:
    """
    Login to backend API and get auth token.

    Args:
        base_url: Backend API base URL
        username: Login username
        password: Login password

    Returns:
        Auth token string

    Raises:
        RuntimeError: If login fails
    """
    resp = requests.post(
        f"{base_url}/api/auth/login",
        json={"username": username, "password": password},
        timeout=15,
    )
    data = resp.json()
    if data.get("code") != 1:
        raise RuntimeError(f"Login failed: {data.get('msg', 'Unknown error')}")
    return data["data"]["token"]


def call_phase22_backtest(
    base_url: str,
    token: str,
    universe: str,
    start_date: str,
    end_date: str,
    indicator_code: str,
    n_long: int,
    initial_capital: float = 100_000,
    timeout: float = 120.0,
    max_retries: int = 3,
) -> Optional[Dict[str, Any]]:
    """
    Call Phase 22 cross-sectional portfolio backtest API.

    Per D-08: HTTP API call, not direct service reuse.
    Per D-10: Universe -> nq100, n_long -> tradingConfig.n_long.

    Args:
        base_url: Backend API base URL
        token: Auth token
        universe: Universe name (e.g., "nq100")
        start_date: Start date YYYY-MM-DD
        end_date: End date YYYY-MM-DD
        indicator_code: Indicator code string
        n_long: Number of long positions
        initial_capital: Initial capital for portfolio
        timeout: HTTP timeout in seconds
        max_retries: Max retry attempts on transient errors

    Returns:
        Dict with neutral_off, neutral_on, repro if success; None if error
    """
    headers = {"Authorization": f"Bearer {token}"}

    # Per D-03: Never send symbolList, always use universe
    payload = {
        "universe": universe,
        "startDate": start_date,
        "endDate": end_date,
        "indicatorCode": indicator_code,
        "timeframe": "1D",
        "market": "USStock",
        "tradingConfig": {
            "initialCapital": initial_capital,
            "n_long": n_long,
            "rebalanceFrequency": "monthly",
        },
    }

    endpoint = f"{base_url}/api/indicator/cross-sectional-portfolio-backtest"

    for attempt in range(max_retries):
        try:
            resp = requests.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=timeout,
            )
            data = resp.json()

            # Success per D-01: code==1, msg=='OK'
            if data.get("code") == 1:
                return data.get("data")

            # Business error (e.g., pool validation D-03, contract error)
            print(f"  API error: {data.get('msg', 'Unknown error')}")
            return None

        except requests.Timeout:
            if attempt < max_retries - 1:
                print(f"  Timeout, retry {attempt + 2}/{max_retries}")
                time.sleep(1)
                continue
            print(f"  Timeout after {max_retries} retries")
            return None

        except requests.RequestException as e:
            print(f"  HTTP error: {e}")
            return None

    return None


def build_indicator_code(
    factors: List[str],
    directions: List[int],
) -> str:
    """
    Generate indicator code for a factor combination.

    Per D-10: Factor combo -> Phase 22 indicator code.
    Uses Phase 20 built-in factors via compute_factor_by_name.

    Args:
        factors: List of factor names (e.g., ['MOM_1M', 'VOL_20D'])
        directions: List of factor directions (+1 or -1)

    Returns:
        Indicator code string for Phase 22 API
    """
    # Import Phase 20 built-in factors
    factor_import = "from app.factors.factor_defs import compute_factor_by_name"

    # Compute each factor
    factor_compute_lines = []
    for f in factors:
        factor_compute_lines.append(
            f"factor_{f} = compute_factor_by_name('{f}', close, volume)"
        )

    # Composite score: weighted rank combination
    n_factors = len(factors)
    weight = 1.0 / n_factors

    score_lines = []
    for i, (f, d) in enumerate(zip(factors, directions)):
        score_lines.append(
            f"    ranked_{f} = factor_{f}.rank(pct=True)\n"
            f"    composite += {d} * ranked_{f} * {weight}"
        )

    # Build indicator code per Phase 22 D-07, D-08 contract
    code = f'''
{factor_import}
close = data[symbol]["close"]
volume = data[symbol].get("volume", None)

# Compute factors
{chr(10).join(factor_compute_lines)}

# Composite score
composite = pd.Series(0.0, index=data.keys())
for symbol in data.keys():
    try:
{chr(10).join(score_lines)}
    except Exception:
        pass

# Select top n_long symbols (from trading_config)
n_long = trading_config.get("n_long", 20)
sorted_symbols = composite.sort_values(ascending=False).head(n_long).index.tolist()

# Assign scores and weights per Phase 22 D-07, D-08
for s in symbols:
    scores[s] = composite.get(s, 0.0)

for s in sorted_symbols:
    weights[s] = 1.0 / n_long

rankings = sorted_symbols
'''

    return code


def compute_score(summary: Optional[Dict[str, Any]]) -> float:
    """
    Compute ranking score for a backtest result.

    Per SCRIPT-02: Standard metrics ranking formula.
    Formula from prototype: weighted combination of annual return, Sharpe, Calmar, MaxDD, WinRate.

    Args:
        summary: Dict with annualReturn, sharpeRatio, maxDrawdown, calmarRatio, winRate
                 or None for failed backtest

    Returns:
        Score value (higher = better). Returns -9999 for None.
    """
    if summary is None:
        return -9999.0

    # Extract values with defaults for missing fields
    a = summary.get("annualReturn", 0) or 0          # Annual return %
    s = summary.get("sharpeRatio", 0) or 0           # Sharpe ratio
    d = abs(summary.get("maxDrawdown", -100) or -100)  # Max drawdown (absolute)
    c = summary.get("calmarRatio", 0) or 0           # Calmar ratio
    w = summary.get("winRate", 0) or 0               # Win rate %

    # Formula per prototype (Claude's Discretion: score weights)
    # - Annual return: 25% weight
    # - Sharpe (scaled by 10): 30% weight
    # - Calmar (capped at 5, scaled by 5): 15% weight
    # - MaxDD (penalty): 15% weight
    # - WinRate (capped at 70): 15% weight
    score = (
        a * 0.25
        + s * 10 * 0.30
        + min(c, 5) * 5 * 0.15
        - d * 0.15
        + min(w, 70) * 0.15
    )

    return round(score, 4)


def run_single_backtest(
    base_url: str,
    token: str,
    config: Dict[str, Any],
    factor_combo: Dict[str, Any],
    n_long: int,
    start_date: str,
    end_date: str,
) -> Optional[Dict[str, Any]]:
    """
    Run a single backtest for a factor combination.

    Per D-11: Process both neutral_off and neutral_on results.
    Per D-12: Return scores for both neutralization modes.

    Args:
        base_url: Backend API URL
        token: Auth token
        config: Full config dict (for defaults)
        factor_combo: Dict with 'factors' and 'directions'
        n_long: Number of long positions
        start_date: Start date YYYY-MM-DD
        end_date: End date YYYY-MM-DD

    Returns:
        Dict with factors, n_long, neutral_off_score, neutral_on_score, summaries
        or None if API call failed
    """
    # Build indicator code per D-10
    indicator_code = build_indicator_code(
        factor_combo['factors'],
        factor_combo['directions'],
    )

    # Get defaults from config
    bt_defaults = config.get('backtest_defaults', {})
    universe = bt_defaults.get('universe', 'nq100')
    initial_capital = bt_defaults.get('initial_capital', 100_000)

    # Call Phase 22 API
    data = call_phase22_backtest(
        base_url=base_url,
        token=token,
        universe=universe,
        start_date=start_date,
        end_date=end_date,
        indicator_code=indicator_code,
        n_long=n_long,
        initial_capital=initial_capital,
    )

    if data is None:
        return None

    # Process both neutralization modes per D-11, D-12
    neutral_off_summary = data.get('neutral_off', {}).get('summary')
    neutral_on_summary = data.get('neutral_on', {}).get('summary')

    neutral_off_score = compute_score(neutral_off_summary)
    neutral_on_score = compute_score(neutral_on_summary)

    return {
        'factors': factor_combo['factors'],
        'directions': factor_combo['directions'],
        'n_long': n_long,
        'start_date': start_date,
        'end_date': end_date,
        'neutral_off_score': neutral_off_score,
        'neutral_on_score': neutral_on_score,
        'neutral_off_summary': neutral_off_summary,
        'neutral_on_summary': neutral_on_summary,
        'repro': data.get('repro'),
    }


# ═══════════════════════════════════════════════════════════════
# Checkpoint Resume (SCRIPT-03)
# ═══════════════════════════════════════════════════════════════

def load_checkpoint(ckpt_path: str) -> Tuple[Set[str], List[Dict[str, Any]]]:
    """
    Load checkpoint file for resume support.

    Per D-17: checkpoint.json records completed backtests.
    Key format: "{factor_combo_str}|{n_long}|{window_id}"

    Args:
        ckpt_path: Path to checkpoint.json

    Returns:
        Tuple of (done_keys set, cached_results list)
        Returns (empty set, empty list) if file doesn't exist
    """
    if not os.path.exists(ckpt_path):
        return set(), []

    try:
        with open(ckpt_path, 'r') as f:
            data = json.load(f)
        done_keys = set(data.get('done', []))
        cached_results = data.get('results', [])
        return done_keys, cached_results
    except (json.JSONDecodeError, IOError):
        # Corrupted checkpoint - start fresh
        print(f"Warning: Corrupted checkpoint at {ckpt_path}, starting fresh")
        return set(), []


def save_checkpoint(ckpt_path: str, done_keys: Set[str], results: List[Dict[str, Any]]) -> None:
    """
    Save checkpoint file for resume support.

    Per D-17: checkpoint.json for fault tolerance.

    Args:
        ckpt_path: Path to checkpoint.json
        done_keys: Set of completed backtest keys
        results: List of all results so far
    """
    with open(ckpt_path, 'w') as f:
        json.dump({
            'done': list(done_keys),
            'results': results,
        }, f, default=str)


def make_checkpoint_key(factors: List[str], n_long: int, window_id: Optional[int] = None) -> str:
    """
    Generate checkpoint key for a backtest configuration.

    Key format per D-17: "{factor_combo_str}|{n_long}|{window_id}"

    Args:
        factors: List of factor names
        n_long: Number of long positions
        window_id: Walk-forward window ID (None for simple mode)

    Returns:
        Unique string key for checkpoint
    """
    factor_str = '+'.join(factors)
    window_suffix = f"|w{window_id}" if window_id is not None else ""
    return f"{factor_str}|{n_long}{window_suffix}"


# ═══════════════════════════════════════════════════════════════
# Output Functions (SCRIPT-02: JSONL, CSV, HTML)
# ═══════════════════════════════════════════════════════════════

def append_result_jsonl(jsonl_path: str, result: Dict[str, Any]) -> None:
    """
    Append a result to JSONL file incrementally.

    Per D-14, D-17: JSONL for incremental output supporting checkpoint.

    Args:
        jsonl_path: Path to all_results.jsonl
        result: Result dict to append
    """
    # Ensure parent directory exists
    os.makedirs(os.path.dirname(jsonl_path), exist_ok=True)

    with open(jsonl_path, 'a') as f:
        f.write(json.dumps(result, ensure_ascii=False, default=str) + '\n')


def export_results_csv(results: List[Dict[str, Any]], csv_path: str, neutral_mode: str = 'off') -> None:
    """
    Export results to CSV for analysis.

    Per D-14, D-15: CSV export with standard fields.

    Args:
        results: List of result dicts
        csv_path: Path to output CSV
        neutral_mode: 'off' or 'on' for which summary to use
    """
    # Build DataFrame with D-15 specified fields
    rows = []
    for r in results:
        summary_key = f'neutral_{neutral_mode}_summary'
        summary = r.get(summary_key) or {}

        row = {
            'factors': '+'.join(r.get('factors', [])),
            'n_long': r.get('n_long', 0),
            'annualReturn': summary.get('annualReturn', 0) or 0,
            'sharpeRatio': summary.get('sharpeRatio', 0) or 0,
            'calmarRatio': summary.get('calmarRatio', 0) or 0,
            'maxDrawdown': summary.get('maxDrawdown', 0) or 0,
            'winRate': summary.get('winRate', 0) or 0,
            'totalMonths': summary.get('totalMonths', 0) or 0,
            'score': r.get(f'neutral_{neutral_mode}_score', -9999),
            'window_id': r.get('window_id', None),
        }
        rows.append(row)

    df = pd.DataFrame(rows)

    # Ensure parent directory exists
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    df.to_csv(csv_path, index=False)


def generate_html_report(
    results: List[Dict[str, Any]],
    config: Dict[str, Any],
    output_path: str,
    neutral_mode: str = 'off',
) -> None:
    """
    Generate HTML visualization report.

    Per D-16: Report includes config summary, TOP 20, factor frequency, holdings best.

    Args:
        results: List of result dicts (sorted by score)
        config: Config dict for summary display
        output_path: Path to output HTML file
        neutral_mode: 'off' or 'on' for which results to display
    """
    from datetime import datetime

    # Sort by score
    score_key = f'neutral_{neutral_mode}_score'
    sorted_results = sorted(results, key=lambda x: x.get(score_key, -9999), reverse=True)

    top20 = sorted_results[:20]

    # Factor frequency in TOP 100 per D-16
    factor_stats = {}
    for r in sorted_results[:100]:
        for f in r.get('factors', []):
            factor_stats[f] = factor_stats.get(f, 0) + 1

    # Build HTML using f-string (Claude's Discretion: no Jinja2)
    html = f'''<!DOCTYPE html>
<html>
<head>
<title>NQ100 Grid Search Report</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; }}
h1, h2 {{ color: #333; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background-color: #f4f4f4; }}
tr:nth-child(even) {{ background-color: #f9f9f9; }}
.positive {{ color: green; }}
.negative {{ color: red; }}
</style>
</head>
<body>
<h1>NQ100 Cross-Sectional Grid Search Report</h1>

<h2>Configuration</h2>
<ul>
<li>Factors: {len(config['search_space']['factors'])} available</li>
<li>Combo sizes: {config['search_space']['combo_min']} to {config['search_space']['combo_max']}</li>
<li>Holdings: {config['search_space']['n_long_options']}</li>
<li>Walk-forward: {config.get('walk_forward', {}).get('enabled', False)}</li>
</ul>

<h2>Top 20 Results (Neutral {neutral_mode.upper()})</h2>
<table>
<tr><th>#</th><th>Factors</th><th>Holdings</th><th>Ann Return</th><th>Sharpe</th><th>MaxDD</th><th>Score</th></tr>
'''

    for i, r in enumerate(top20):
        summary_key = f'neutral_{neutral_mode}_summary'
        summary = r.get(summary_key) or {}
        ann = summary.get('annualReturn', 0) or 0
        shr = summary.get('sharpeRatio', 0) or 0
        dd = summary.get('maxDrawdown', 0) or 0
        sc = r.get(score_key, 0) or 0
        factors_str = ', '.join(r.get('factors', []))

        ann_class = 'positive' if ann >= 0 else 'negative'

        html += f'''<tr>
<td>{i+1}</td>
<td>{factors_str}</td>
<td>{r.get('n_long', 0)}</td>
<td class="{ann_class}">{ann:+.1f}%</td>
<td>{shr:.2f}</td>
<td class="negative">{dd:.1f}%</td>
<td>{sc:.1f}</td>
</tr>'''

    html += f'''</table>

<h2>Factor Frequency (Top 100)</h2>
<table>
<tr><th>Factor</th><th>Appearances</th><th>Percentage</th></tr>
'''

    for f, count in sorted(factor_stats.items(), key=lambda x: -x[1]):
        pct = count / min(100, len(sorted_results)) * 100
        html += f'''<tr><td>{f}</td><td>{count}</td><td>{pct:.0f}%</td></tr>'''

    html += '''</table>

<h2>Best by Holdings</h2>
<table>
<tr><th>Holdings</th><th>Best Factors</th><th>Score</th></tr>
'''

    # Best by n_long
    n_long_options = config['search_space']['n_long_options']
    for nl in n_long_options:
        nl_results = [r for r in sorted_results if r.get('n_long') == nl]
        if nl_results:
            best = nl_results[0]
            factors_str = ', '.join(best.get('factors', []))
            sc = best.get(score_key, 0)
            html += f'''<tr><td>{nl}</td><td>{factors_str}</td><td>{sc:.1f}</td></tr>'''

    html += f'''</table>

<p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
<p>Total results: {len(results)}</p>
</body>
</html>'''

    # Ensure parent directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w') as f:
        f.write(html)


# ═══════════════════════════════════════════════════════════════
# Walk-Forward Validation (SCRIPT-04)
# ═══════════════════════════════════════════════════════════════

def generate_walk_forward_windows(
    start_date: str,
    end_date: str,
    train_months: int,
    test_months: int,
    step_months: int,
) -> List[Dict[str, Any]]:
    """
    Generate walk-forward window definitions.

    Per D-04: Rolling fixed-size windows with fixed step.
    Per D-05: Params from config (train_months, test_months, step_months).

    Args:
        start_date: Start date YYYY-MM-DD
        end_date: End date YYYY-MM-DD
        train_months: Training window length in months
        test_months: Test window length in months
        step_months: Slide step in months

    Returns:
        List of window dicts with window_id, train_start/end, test_start/end
    """
    # Convert to datetime
    start = datetime.strptime(start_date[:10], '%Y-%m-%d')
    end = datetime.strptime(end_date[:10], '%Y-%m-%d')

    # Approximate month lengths (30 days average)
    train_len = timedelta(days=train_months * 30)
    test_len = timedelta(days=test_months * 30)
    step_len = timedelta(days=step_months * 30)

    windows = []
    window_start = start

    while window_start + train_len + test_len <= end:
        train_end = window_start + train_len
        test_end = train_end + test_len

        windows.append({
            'window_id': len(windows) + 1,
            'train_start': window_start.strftime('%Y-%m-%d'),
            'train_end': train_end.strftime('%Y-%m-%d'),
            'test_start': train_end.strftime('%Y-%m-%d'),  # Per D-06: test starts after train
            'test_end': test_end.strftime('%Y-%m-%d'),
        })

        # Slide forward per D-04
        window_start += step_len

    return windows


def aggregate_oos_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Extract and aggregate out-of-sample (test phase) results.

    Per D-07: OOS summary includes window bests, aggregate stats.

    Args:
        results: All results from grid search

    Returns:
        List of OOS (test phase) results
    """
    oos_results = [r for r in results if r.get('phase') == 'test' and r.get('oos')]
    return oos_results


def compute_oos_summary(oos_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute aggregate statistics for OOS results.

    Per D-07: Average OOS Sharpe, annual return, stability indicators.

    Args:
        oos_results: List of test phase results

    Returns:
        Dict with avg_sharpe, avg_annual_return, avg_score, window_count
    """
    if not oos_results:
        return {
            'avg_sharpe': 0,
            'avg_annual_return': 0,
            'avg_score': -9999,
            'window_count': 0,
        }

    sharpes = []
    ann_returns = []
    scores = []

    for r in oos_results:
        summary = r.get('neutral_off_summary') or {}
        sharpes.append(summary.get('sharpeRatio', 0) or 0)
        ann_returns.append(summary.get('annualReturn', 0) or 0)
        scores.append(r.get('neutral_off_score', -9999))

    return {
        'avg_sharpe': sum(sharpes) / len(sharpes),
        'avg_annual_return': sum(ann_returns) / len(ann_returns),
        'avg_score': sum(scores) / len(scores),
        'window_count': len(oos_results),
    }


def save_top100_outputs(
    results: List[Dict[str, Any]],
    output_dir: str,
) -> None:
    """
    Save TOP 100 results for both neutralization modes.

    Per D-12: Two separate outputs:
      - neutral_off_top100.json: best without neutralization
      - neutral_on_top100.json: best with neutralization

    Args:
        results: All results from grid search
        output_dir: Output directory
    """
    os.makedirs(output_dir, exist_ok=True)

    # Sort by neutral_off_score
    sorted_off = sorted(results, key=lambda x: x.get('neutral_off_score', -9999), reverse=True)
    top100_off = sorted_off[:100]

    # Simplify for output (remove full summary, keep key fields)
    top100_off_simplified = []
    for r in top100_off:
        simplified = {
            'factors': r.get('factors', []),
            'n_long': r.get('n_long', 0),
            'score': r.get('neutral_off_score', -9999),
            'annualReturn': (r.get('neutral_off_summary') or {}).get('annualReturn', 0),
            'sharpeRatio': (r.get('neutral_off_summary') or {}).get('sharpeRatio', 0),
            'maxDrawdown': (r.get('neutral_off_summary') or {}).get('maxDrawdown', 0),
            'window_id': r.get('window_id'),
            'phase': r.get('phase'),
        }
        top100_off_simplified.append(simplified)

    with open(os.path.join(output_dir, 'neutral_off_top100.json'), 'w') as f:
        json.dump(top100_off_simplified, f, indent=2, default=str)

    # Sort by neutral_on_score
    sorted_on = sorted(results, key=lambda x: x.get('neutral_on_score', -9999), reverse=True)
    top100_on = sorted_on[:100]

    top100_on_simplified = []
    for r in top100_on:
        simplified = {
            'factors': r.get('factors', []),
            'n_long': r.get('n_long', 0),
            'score': r.get('neutral_on_score', -9999),
            'annualReturn': (r.get('neutral_on_summary') or {}).get('annualReturn', 0),
            'sharpeRatio': (r.get('neutral_on_summary') or {}).get('sharpeRatio', 0),
            'maxDrawdown': (r.get('neutral_on_summary') or {}).get('maxDrawdown', 0),
            'window_id': r.get('window_id'),
            'phase': r.get('phase'),
        }
        top100_on_simplified.append(simplified)

    with open(os.path.join(output_dir, 'neutral_on_top100.json'), 'w') as f:
        json.dump(top100_on_simplified, f, indent=2, default=str)


def run_walk_forward_grid_search(
    base_url: str,
    token: str,
    config: Dict[str, Any],
    output_dir: str,
) -> List[Dict[str, Any]]:
    """
    Run walk-forward grid search with training/test windows.

    Per D-06: Each window:
      1. Training: grid search for best combo
      2. Test: evaluate best combo on out-of-sample period
      3. Slide to next window

    Per D-18: Serial execution, no parallel calls.
    Per D-19: Progress output every N backtests.

    Args:
        base_url: Backend API URL
        token: Auth token
        config: Full config dict
        output_dir: Output directory path

    Returns:
        List of all results (train + test) across all windows
    """
    ss = config['search_space']
    wf = config.get('walk_forward', {})
    output_cfg = config.get('output', {})

    # Generate factor combinations
    combos = generate_factor_combinations(
        ss['factors'],
        ss['combo_min'],
        ss['combo_max'],
    )
    n_long_options = ss['n_long_options']

    # Generate walk-forward windows (if enabled)
    if wf.get('enabled', False):
        start_date = wf.get('start_date') or config.get('backtest_defaults', {}).get('start_date', '2020-01-01')
        end_date = wf.get('end_date') or config.get('backtest_defaults', {}).get('end_date', '2026-04-01')
        windows = generate_walk_forward_windows(
            start_date,
            end_date,
            wf['train_months'],
            wf['test_months'],
            wf['step_months'],
        )
    else:
        # Single window for non-walk-forward mode
        start_date = config.get('backtest_defaults', {}).get('start_date', '2021-04-01')
        end_date = config.get('backtest_defaults', {}).get('end_date', '2026-04-01')
        windows = [{
            'window_id': 1,
            'train_start': start_date,
            'train_end': end_date,
            'test_start': None,  # No test phase when walk_forward disabled
            'test_end': None,
        }]

    # Setup output paths
    os.makedirs(output_dir, exist_ok=True)
    jsonl_path = os.path.join(output_dir, 'all_results.jsonl')
    ckpt_path = os.path.join(output_dir, 'checkpoint.json')

    # Load checkpoint per D-17
    done_keys, _ = load_checkpoint(ckpt_path)

    # Progress interval per D-19
    progress_interval = output_cfg.get('progress_interval', 50)

    all_results = []
    total_backtests = len(combos) * len(n_long_options) * len(windows) * 2  # train + test (approximate)
    completed = 0
    start_time = time.time()

    print(f"\n{'='*80}")
    print(f"  Walk-Forward Grid Search")
    print(f"  {len(combos)} combos x {len(n_long_options)} holdings x {len(windows)} windows")
    print(f"  Total backtests: ~{total_backtests}")
    print(f"{'='*80}\n")

    for window in windows:
        window_id = window['window_id']

        # === Training Phase: Grid search on train period ===
        train_best = None
        train_best_score = -9999.0
        train_best_n_long = None

        for combo in combos:
            for n_long in n_long_options:
                # Checkpoint key per D-17
                key = make_checkpoint_key(combo['factors'], n_long, window_id)

                if key in done_keys:
                    completed += 1
                    continue

                # Run backtest on training period
                result = run_single_backtest(
                    base_url, token, config, combo, n_long,
                    window['train_start'], window['train_end'],
                )

                if result:
                    result['window_id'] = window_id
                    result['phase'] = 'train'
                    all_results.append(result)
                    append_result_jsonl(jsonl_path, result)
                    done_keys.add(key)
                    completed += 1

                    # Track best per D-06
                    score = result.get('neutral_off_score', -9999)
                    if score > train_best_score:
                        train_best = combo
                        train_best_score = score
                        train_best_n_long = n_long

                # Progress output per D-19
                if completed % progress_interval == 0:
                    elapsed = time.time() - start_time
                    rate = completed / elapsed if elapsed > 0 else 0
                    eta = (total_backtests - completed) / rate / 60 if rate > 0 else 0
                    print(f"  [{completed:5d}/{total_backtests}] Window {window_id} Train "
                          f"Rate={rate:.1f}/s ETA={eta:.1f}min")

        # === Test Phase: Evaluate best combo on test period ===
        if train_best and window.get('test_start'):
            test_key = make_checkpoint_key(train_best['factors'], train_best_n_long, window_id)
            test_key += '_test'  # Distinguish test from train

            if test_key not in done_keys:
                result = run_single_backtest(
                    base_url, token, config, train_best, train_best_n_long,
                    window['test_start'], window['test_end'],
                )

                if result:
                    result['window_id'] = window_id
                    result['phase'] = 'test'
                    result['oos'] = True  # Out-of-sample marker
                    all_results.append(result)
                    append_result_jsonl(jsonl_path, result)
                    done_keys.add(test_key)
                    completed += 1

        # Save checkpoint after each window
        save_checkpoint(ckpt_path, done_keys, all_results)

    return all_results


# ═══════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════

def main():
    """
    Main entry point for grid search script.

    Workflow per D-14 through D-19:
      1. Parse CLI args
      2. Load config
      3. Login to API
      4. Run walk-forward grid search
      5. Export CSV for both neutral modes
      6. Generate HTML reports
      7. Save TOP 100 outputs
      8. Print summary
    """
    args = parse_args()

    print("=" * 80)
    print("  NQ100 Cross-Sectional Grid Search")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # 1. Load config per D-01
    print(f"\n[1/6] Loading config: {args.config}")
    config = load_config(args.config)

    # 2. Login to API per D-08
    print(f"\n[2/6] Connecting to API: {args.base_url}")
    if args.token:
        token = args.token
    else:
        token = login(args.base_url, args.username, args.password)
    print(f"  Authenticated successfully")

    # 3. Run grid search per D-04 through D-06
    print(f"\n[3/6] Running grid search...")
    results = run_walk_forward_grid_search(
        args.base_url,
        token,
        config,
        args.output_dir,
    )
    print(f"  Completed: {len(results)} results")

    # 4. Export CSV per D-14, D-15
    print(f"\n[4/6] Exporting CSV...")
    csv_path = os.path.join(args.output_dir, 'all_results.csv')
    export_results_csv(results, csv_path, neutral_mode='off')

    csv_path_on = os.path.join(args.output_dir, 'all_results_neutral_on.csv')
    export_results_csv(results, csv_path_on, neutral_mode='on')

    # 5. Generate HTML reports per D-16
    print(f"\n[5/6] Generating HTML reports...")
    html_path = os.path.join(args.output_dir, 'report.html')
    generate_html_report(results, config, html_path, neutral_mode='off')

    html_path_on = os.path.join(args.output_dir, 'report_neutral_on.html')
    generate_html_report(results, config, html_path_on, neutral_mode='on')

    # 6. Save TOP 100 outputs per D-12
    print(f"\n[6/6] Saving TOP 100 results...")
    save_top100_outputs(results, args.output_dir)

    # OOS summary if walk_forward enabled
    if config.get('walk_forward', {}).get('enabled', False):
        oos_results = aggregate_oos_results(results)
        oos_summary = compute_oos_summary(oos_results)
        print(f"\n{'='*60}")
        print(f"  Walk-Forward Out-of-Sample Summary")
        print(f"{'='*60}")
        print(f"  Windows: {oos_summary['window_count']}")
        print(f"  Avg Sharpe: {oos_summary['avg_sharpe']:.2f}")
        print(f"  Avg Annual Return: {oos_summary['avg_annual_return']:.1f}%")
        print(f"  Avg Score: {oos_summary['avg_score']:.1f}")

    # Final output summary
    print(f"\n{'='*80}")
    print(f"  Output files:")
    print(f"    {args.output_dir}/all_results.jsonl")
    print(f"    {args.output_dir}/all_results.csv")
    print(f"    {args.output_dir}/report.html")
    print(f"    {args.output_dir}/neutral_off_top100.json")
    print(f"    {args.output_dir}/neutral_on_top100.json")
    print(f"    {args.output_dir}/checkpoint.json")
    print(f"{'='*80}")
    print(f"\n  Grid search complete!")


if __name__ == "__main__":
    main()