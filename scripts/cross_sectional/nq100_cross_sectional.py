#!/usr/bin/env python3
"""
NQ100 截面策略回测 + 因子组合暴力搜索

搜索空间:
  - 12 个价格因子的所有 1~4 因子子集 = 793 种组合
  - × 7 种持仓数 (10,15,20,30,40,50,60) = 5,551 次回测
  - 月度调仓, 等权, 纯多头

特性:
  - 全量 NQ100 成分股 (~101 只)
  - 每次调仓按数据可用性自动筛选（处理成分股变动）
  - union 日期面板（不要求所有股票同时有数据）
  - 5 年回测 (2021-04 ~ 2026-04)
  - 本地 CSV 缓存 + QuantDinger DB 缓存双重加速
  - 断点续传

用法:
  # 本地 (WSL → NAS)
  python3 -u nq100_cross_sectional.py

  # 服务器后台 (SSH 容器内)
  nohup python3 -u nq100_cross_sectional.py --base-url http://quantdinger-backend:5000 > run.log 2>&1 &
  tail -f run.log
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from itertools import combinations

import numpy as np
import pandas as pd
import requests

# ═══════════════════════════════════════════════════════════════
# NQ100 成分股 — 当前全量 + 近年进出的股票，保证覆盖面
# 每次调仓时只选有充足数据的子集，自然处理成分变动
# ═══════════════════════════════════════════════════════════════

NQ100_UNIVERSE = [
    # ── 当前 NQ100 成分 (2026 Q1) ──
    "AAPL",  "ABNB",  "ADBE",  "ADI",   "ADP",   "ADSK",  "AEP",   "AMAT",
    "AMGN",  "AMZN",  "ANSS",  "ARM",   "ASML",  "AVGO",  "AZN",   "BIIB",
    "BKNG",  "BKR",   "CDNS",  "CDW",   "CEG",   "CHTR",  "CMCSA", "COST",
    "CPRT",  "CRWD",  "CSCO",  "CSGP",  "CTAS",  "CTSH",  "DASH",  "DDOG",
    "DLTR",  "DXCM",  "EA",    "EXC",   "FANG",  "FAST",  "FTNT",  "GEHC",
    "GFS",   "GILD",  "GOOGL", "HON",   "IDXX",  "ILMN",  "INTC",  "INTU",
    "ISRG",  "KDP",   "KHC",   "KLAC",  "LRCX",  "LULU",  "MAR",   "MCHP",
    "MDLZ",  "MELI",  "META",  "MNST",  "MRNA",  "MRVL",  "MSFT",  "MU",
    "NFLX",  "NVDA",  "NXPI",  "ODFL",  "ON",    "ORLY",  "PANW",  "PAYX",
    "PCAR",  "PDD",   "PEP",   "PYPL",  "QCOM",  "REGN",  "ROP",   "ROST",
    "SBUX",  "SMCI",  "SNPS",  "TEAM",  "TMUS",  "TSLA",  "TTD",   "TTWO",
    "TXN",   "VRSK",  "WDAY",  "WBD",   "XEL",   "ZS",
    # ── 近年曾在 NQ100 / 热门纳斯达克 ──
    "AMD",   "ALGN",  "DOCU",  "ENPH",  "JD",    "LCID",  "LI",    "LULU",
    "NTES",  "OKTA",  "PTON",  "RIVN",  "SIRI",  "SPLK",  "SWKS",  "WYNN",
    "ZM",    "ZS",
]

# 去重
NQ100_UNIVERSE = sorted(set(NQ100_UNIVERSE))

# ═══════════════════════════════════════════════════════════════
# 因子定义
# ═══════════════════════════════════════════════════════════════

FACTOR_DEFS = {
    "MOM_1M":     {"type": "mom",      "w": 21,                "dir":  1, "d": "1月动量"},
    "MOM_3M":     {"type": "mom",      "w": 63,                "dir":  1, "d": "3月动量"},
    "MOM_6M":     {"type": "mom",      "w": 126,               "dir":  1, "d": "6月动量"},
    "MOM_12M_1M": {"type": "mom_skip", "w": 252, "skip": 21,   "dir":  1, "d": "12月跳1月"},
    "REV_1W":     {"type": "rev",      "w": 5,                 "dir": -1, "d": "1周反转"},
    "REV_2W":     {"type": "rev",      "w": 10,                "dir": -1, "d": "2周反转"},
    "VOL_20D":    {"type": "vol",      "w": 20,                "dir": -1, "d": "20日波动"},
    "VOL_60D":    {"type": "vol",      "w": 60,                "dir": -1, "d": "60日波动"},
    "DIST_MA50":  {"type": "dist_ma",  "w": 50,                "dir": -1, "d": "偏离MA50"},
    "DIST_MA200": {"type": "dist_ma",  "w": 200,               "dir": -1, "d": "偏离MA200"},
    "VOL_RATIO":  {"type": "vol_ratio","w": 20, "lw": 60,      "dir": -1, "d": "量比20/60"},
    "SHARPE_60D": {"type": "sharpe",   "w": 60,                "dir":  1, "d": "60日Sharpe"},
}

ALL_FACTORS = list(FACTOR_DEFS.keys())
N_LONG_OPTIONS = [10, 15, 20, 30, 40, 50, 60]
MAX_COMBO_SIZE = 4


# ═══════════════════════════════════════════════════════════════
# 数据获取
# ═══════════════════════════════════════════════════════════════

def login(base_url, user, pwd):
    r = requests.post(f"{base_url}/api/auth/login",
                      json={"username": user, "password": pwd}, timeout=15)
    d = r.json()
    if d.get("code") != 1:
        raise RuntimeError(f"Login failed: {d}")
    return d["data"]["token"]


def fetch_kline(base_url, token, symbol, limit=2000):
    """分页拉取日线, QuantDinger 后端会自动缓存到 DB"""
    hdrs = {"Authorization": f"Bearer {token}"}
    bars = []
    before = None
    while True:
        p = {"market": "USStock", "symbol": symbol, "timeframe": "1D", "limit": limit}
        if before:
            p["before_time"] = before
        try:
            r = requests.get(f"{base_url}/api/indicator/kline", params=p,
                             headers=hdrs, timeout=30)
            batch = r.json().get("data", [])
        except Exception:
            break
        if not batch:
            break
        bars.extend(batch)
        if len(batch) < limit:
            break
        before = batch[0]["time"]
        time.sleep(0.35)
    if not bars:
        return pd.DataFrame()
    df = pd.DataFrame(bars)
    df["date"] = pd.to_datetime(df["time"], unit="s")
    return df.sort_values("date").drop_duplicates("date").reset_index(drop=True)


def load_all_data(base_url, token, symbols, cache_dir):
    """加载所有品种数据, 本地 CSV 缓存 + API 拉取"""
    os.makedirs(cache_dir, exist_ok=True)
    data = {}
    n = len(symbols)
    for i, sym in enumerate(symbols):
        cf = os.path.join(cache_dir, f"{sym}.csv")
        tag = f"[{i+1:3d}/{n}] {sym}"

        if os.path.exists(cf) and (time.time() - os.path.getmtime(cf)) / 3600 < 48:
            try:
                df = pd.read_csv(cf, parse_dates=["date"])
                if len(df) >= 252:
                    data[sym] = df
                    print(f"  {tag}: cache {len(df)} bars")
                    continue
            except Exception:
                pass

        print(f"  {tag}: fetch...", end="", flush=True)
        try:
            df = fetch_kline(base_url, token, sym)
        except Exception as e:
            print(f" ERR ({e})")
            continue
        if len(df) < 252:
            print(f" skip ({len(df)} bars < 252)")
            continue
        df.to_csv(cf, index=False)
        data[sym] = df
        d0 = df["date"].iloc[0].strftime("%Y-%m")
        d1 = df["date"].iloc[-1].strftime("%Y-%m")
        print(f" {len(df)} bars ({d0}~{d1})")
        time.sleep(0.35)

    return data


# ═══════════════════════════════════════════════════════════════
# 因子计算
# ═══════════════════════════════════════════════════════════════

def calc_factor(close, volume, fname):
    cfg = FACTOR_DEFS[fname]
    t, w = cfg["type"], cfg["w"]
    if t == "mom":
        return close.pct_change(w)
    if t == "mom_skip":
        return close.pct_change(w) - close.pct_change(cfg["skip"])
    if t == "rev":
        return close.pct_change(w)
    if t == "vol":
        return close.pct_change().rolling(w).std() * np.sqrt(252)
    if t == "dist_ma":
        ma = close.rolling(w).mean()
        return (close - ma) / ma
    if t == "vol_ratio":
        return volume.rolling(w).mean() / volume.rolling(cfg["lw"]).mean().replace(0, np.nan)
    if t == "sharpe":
        r = close.pct_change()
        return r.rolling(w).mean() / r.rolling(w).std().replace(0, np.nan) * np.sqrt(252)
    return pd.Series(np.nan, index=close.index)


def build_panels(all_data):
    """
    构建价格面板和因子面板, 使用 union 日期（不要求所有股票同时有数据）
    返回: price_panel, returns_panel, factor_panels
    """
    # 收集所有日期的 union
    all_dates = set()
    for df in all_data.values():
        all_dates.update(df["date"].tolist())
    all_dates = sorted(all_dates)
    date_idx = pd.DatetimeIndex(all_dates)

    # 价格面板 (index=date, cols=symbols), 缺数据为 NaN
    price_dict = {}
    vol_dict = {}
    for sym, df in all_data.items():
        s = df.set_index("date")
        price_dict[sym] = s["close"].reindex(date_idx)
        vol_dict[sym] = s["volume"].reindex(date_idx)
    price_panel = pd.DataFrame(price_dict)
    vol_panel = pd.DataFrame(vol_dict)
    returns_panel = price_panel.pct_change()

    # 因子面板
    factor_panels = {}
    for fn in ALL_FACTORS:
        cols = {}
        for sym in all_data:
            cols[sym] = calc_factor(price_panel[sym], vol_panel[sym], fn)
        factor_panels[fn] = pd.DataFrame(cols, index=date_idx)

    return price_panel, returns_panel, factor_panels


# ═══════════════════════════════════════════════════════════════
# 回测引擎
# ═══════════════════════════════════════════════════════════════

def monthly_ends(idx, start, end):
    """取 [start, end] 内每月最后一个交易日"""
    mask = (idx >= pd.Timestamp(start)) & (idx <= pd.Timestamp(end))
    sub = idx[mask]
    if len(sub) < 30:
        return []
    s = pd.Series(sub, index=sub)
    return s.groupby(s.dt.to_period("M")).last().tolist()


def backtest(price_panel, returns_panel, factor_panels,
             fnames, fdirs, n_long, start, end):
    """
    单次截面回测.
    每月末: 取有因子值的股票 → 等权 rank → 排序选 Top N → 持有到下月末.
    """
    rebal = monthly_ends(price_panel.index, start, end)
    if len(rebal) < 3:
        return None

    n_f = len(fnames)
    wts = [1.0 / n_f] * n_f
    equity = 1.0
    daily_rets = []
    month_rets = []

    for i in range(len(rebal) - 1):
        rd, nd = rebal[i], rebal[i + 1]

        # 计算 composite score
        composite = pd.Series(0.0, index=price_panel.columns)
        valid = pd.Series(True, index=price_panel.columns)

        for fn, dr, wt in zip(fnames, fdirs, wts):
            fp = factor_panels[fn]
            cands = fp.index[fp.index <= rd]
            if len(cands) == 0:
                continue
            row = fp.loc[cands[-1]]
            valid &= row.notna()
            composite += dr * row.rank(pct=True) * wt

        # 还要求当月有价格数据
        valid &= price_panel.loc[rd].notna()

        syms = valid[valid].index
        cs = composite[syms]
        actual_n = min(n_long, len(cs))
        if actual_n < 5:
            continue

        picks = cs.nlargest(actual_n).index.tolist()

        # 持有期收益
        pmask = (returns_panel.index > rd) & (returns_panel.index <= nd)
        period = returns_panel.loc[pmask, picks]
        if period.empty:
            continue

        port_daily = period.mean(axis=1)
        for r in port_daily.values:
            if np.isnan(r):
                r = 0.0
            equity *= (1 + r)
            daily_rets.append(r)

        mr = float(np.prod(1 + port_daily.fillna(0).values) - 1)
        month_rets.append(mr)

    if len(daily_rets) < 60:
        return None

    dr = np.array(daily_rets)
    n_days = len(dr)
    total_ret = (equity - 1) * 100
    ann_ret = (equity ** (252 / n_days) - 1) * 100

    cum = np.cumprod(1 + dr)
    rmax = np.maximum.accumulate(cum)
    max_dd = float(((cum - rmax) / rmax).min()) * 100

    mu, sig = dr.mean(), dr.std()
    sharpe = float(mu / sig * np.sqrt(252)) if sig > 0 else 0
    calmar = ann_ret / abs(max_dd) if max_dd != 0 else 0

    win_m = sum(1 for r in month_rets if r > 0)
    win_rate = win_m / max(len(month_rets), 1) * 100

    return {
        "totalReturn": round(total_ret, 2),
        "annualReturn": round(ann_ret, 2),
        "maxDrawdown": round(max_dd, 2),
        "sharpeRatio": round(sharpe, 2),
        "calmarRatio": round(calmar, 2),
        "winRate": round(win_rate, 1),
        "totalMonths": len(month_rets),
        "tradingDays": n_days,
    }


def score(r):
    if r is None:
        return -9999
    a = r.get("annualReturn", 0) or 0
    s = r.get("sharpeRatio", 0) or 0
    d = abs(r.get("maxDrawdown", -100) or -100)
    c = r.get("calmarRatio", 0) or 0
    w = r.get("winRate", 0) or 0
    return round(a * 0.25 + s * 10 * 0.30 + min(c, 5) * 5 * 0.15
                 - d * 0.15 + min(w, 70) * 0.15, 4)


# ═══════════════════════════════════════════════════════════════
# 暴力搜索
# ═══════════════════════════════════════════════════════════════

def all_combos():
    combos = []
    for sz in range(1, MAX_COMBO_SIZE + 1):
        for sub in combinations(ALL_FACTORS, sz):
            combos.append({
                "f": list(sub),
                "d": [FACTOR_DEFS[f]["dir"] for f in sub],
            })
    return combos


def grid_search(price_panel, returns_panel, factor_panels,
                start, end, ckpt_file, output_dir):
    combos = all_combos()
    total = len(combos) * len(N_LONG_OPTIONS)

    done, results = set(), []
    if os.path.exists(ckpt_file):
        with open(ckpt_file) as fh:
            ck = json.load(fh)
        done = set(ck.get("done", []))
        results = ck.get("results", [])
        print(f"  断点恢复: 已完成 {len(done)}, 剩余 {total - len(done)}")

    # 每条结果也追加到 JSONL
    jsonl_path = os.path.join(output_dir, "all_results.jsonl")
    jsonl_existed = os.path.exists(jsonl_path)

    sizes = {}
    for sz in range(1, MAX_COMBO_SIZE + 1):
        cnt = sum(1 for c in combos if len(c["f"]) == sz)
        sizes[sz] = cnt

    print(f"\n{'='*80}")
    print(f"  暴力搜索: {len(combos)} 因子组合 × {len(N_LONG_OPTIONS)} 持仓 = {total} 回测")
    for sz, cnt in sizes.items():
        print(f"    {sz}因子: C(12,{sz}) = {cnt}")
    print(f"  持仓: {N_LONG_OPTIONS}")
    print(f"  区间: {start} ~ {end}")
    print(f"{'='*80}\n")

    idx = 0
    new_cnt = 0
    t0 = time.time()

    for combo in combos:
        fn_str = "+".join(combo["f"])
        for nl in N_LONG_OPTIONS:
            idx += 1
            key = f"{fn_str}|{nl}"
            if key in done:
                continue

            bt = backtest(price_panel, returns_panel, factor_panels,
                          combo["f"], combo["d"], nl, start, end)
            sc = score(bt)

            entry = {"factors": combo["f"], "dirs": combo["d"],
                     "n_long": nl, "score": sc}
            if bt:
                entry.update(bt)

            results.append(entry)
            done.add(key)
            new_cnt += 1

            # 追加 JSONL
            with open(jsonl_path, "a") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

            if new_cnt % 50 == 0:
                elapsed = time.time() - t0
                spd = new_cnt / elapsed if elapsed > 0 else 0
                eta = (total - idx) / spd / 60 if spd > 0 else 0
                if bt:
                    print(f"  [{idx:5d}/{total}] {fn_str:45s} T{nl:2d}  "
                          f"Ann={bt['annualReturn']:+6.1f}%  SR={bt['sharpeRatio']:.2f}  "
                          f"Sc={sc:.1f}  ({spd:.1f}/s ETA {eta:.1f}min)")
                else:
                    print(f"  [{idx:5d}/{total}] {fn_str:45s} T{nl:2d}  SKIP  "
                          f"({spd:.1f}/s ETA {eta:.1f}min)")
                _save_ckpt(ckpt_file, done, results)

    _save_ckpt(ckpt_file, done, results)
    elapsed = time.time() - t0
    print(f"\n  完成! {new_cnt} 回测, {elapsed:.1f}s ({new_cnt/elapsed:.1f}/s)")
    results.sort(key=lambda x: x.get("score", -9999), reverse=True)
    return results


def _save_ckpt(path, done, results):
    with open(path, "w") as f:
        json.dump({"done": list(done), "results": results}, f, default=str)


# ═══════════════════════════════════════════════════════════════
# 报告
# ═══════════════════════════════════════════════════════════════

def report(results):
    TOP = 30
    print(f"\n{'='*115}")
    print(f"  TOP {TOP} 因子组合")
    print(f"{'='*115}")
    hdr = (f"{'#':>3} | {'因子':50s} | {'持仓':>4} | {'年化':>7} | {'总收益':>8} | "
           f"{'回撤':>7} | {'SR':>5} | {'CM':>5} | {'WR':>5} | {'月':>3} | {'Score':>6}")
    print(hdr)
    print("-" * 115)
    for i, r in enumerate(results[:TOP]):
        fs = " + ".join(r.get("factors", []))
        a = r.get("annualReturn", 0) or 0
        t = r.get("totalReturn", 0) or 0
        d = r.get("maxDrawdown", 0) or 0
        s = r.get("sharpeRatio", 0) or 0
        c = r.get("calmarRatio", 0) or 0
        w = r.get("winRate", 0) or 0
        m = r.get("totalMonths", 0) or 0
        sc = r.get("score", 0)
        print(f"{i+1:3d} | {fs:50s} | {r['n_long']:4d} | {a:+6.1f}% | {t:+7.1f}% | "
              f"{d:6.1f}% | {s:5.2f} | {c:5.2f} | {w:4.1f}% | {m:3d} | {sc:6.1f}")
    print("=" * 115)

    # 因子频率
    fstats = {}
    for r in results[:100]:
        for f in r.get("factors", []):
            fstats.setdefault(f, []).append(r.get("score", 0))
    print(f"\n  因子频率 (Top 100 中)")
    print("-" * 70)
    print(f"{'因子':15s} | {'出现':>5} | {'占比':>5} | {'平均Score':>8} | {'描述'}")
    print("-" * 70)
    for fn, scs in sorted(fstats.items(), key=lambda x: -len(x[1])):
        print(f"{fn:15s} | {len(scs):5d} | {len(scs):4d}% | {np.mean(scs):8.1f} | {FACTOR_DEFS[fn]['d']}")

    # 各持仓最优
    print(f"\n  各持仓数最优")
    print("-" * 100)
    for nl in N_LONG_OPTIONS:
        fl = [r for r in results if r.get("n_long") == nl]
        if fl:
            b = fl[0]
            fs = " + ".join(b.get("factors", []))
            a = b.get("annualReturn", 0) or 0
            s = b.get("sharpeRatio", 0) or 0
            d = b.get("maxDrawdown", 0) or 0
            print(f"  Top{nl:2d}: {fs:50s}  Ann={a:+.1f}%  SR={s:.2f}  DD={d:.1f}%")

    # 最优方案
    if results:
        b = results[0]
        print(f"\n{'='*80}")
        print(f"  BEST: {' + '.join(b['factors'])}")
        print(f"  持仓 Top{b['n_long']}  年化{b.get('annualReturn',0):+.1f}%  "
              f"总收益{b.get('totalReturn',0):+.1f}%  回撤{b.get('maxDrawdown',0):.1f}%  "
              f"SR={b.get('sharpeRatio',0):.2f}  Calmar={b.get('calmarRatio',0):.2f}  "
              f"月胜率{b.get('winRate',0):.1f}%")
        print(f"{'='*80}")


def save_results(results, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "top100.json"), "w") as f:
        json.dump(results[:100], f, indent=2, ensure_ascii=False, default=str)
    summary = {
        "run_time": datetime.now().isoformat(),
        "total_combos": len(results),
        "factors": ALL_FACTORS,
        "n_long_options": N_LONG_OPTIONS,
        "top20": results[:20],
    }
    with open(os.path.join(output_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  结果: {output_dir}/")
    print(f"    all_results.jsonl  全量")
    print(f"    top100.json        Top 100")
    print(f"    summary.json       摘要")


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="NQ100 截面策略暴力搜索")
    ap.add_argument("--base-url", default="http://hgq-nas:35000")
    ap.add_argument("--username", default="backtest_bot")
    ap.add_argument("--password", default="backtest123")
    ap.add_argument("--start", default="2021-04-01")
    ap.add_argument("--end", default="2026-04-01")
    ap.add_argument("--cache-dir", default="cache")
    ap.add_argument("--output-dir", default="results")
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    print("=" * 80)
    print("  NQ100 截面策略 — 因子暴力搜索")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # 1. Login
    print("\n[1/4] 登录...")
    token = login(args.base_url, args.username, args.password)
    print(f"  OK ({args.username})")

    # 2. Data
    print(f"\n[2/4] 加载 {len(NQ100_UNIVERSE)} 只股票日线 (本地缓存+API)...")
    all_data = load_all_data(args.base_url, token, NQ100_UNIVERSE, args.cache_dir)
    print(f"\n  有效品种: {len(all_data)}/{len(NQ100_UNIVERSE)}")
    if len(all_data) < 30:
        print("  ERROR: 有效品种 < 30, 无法运行截面策略")
        sys.exit(1)

    # 3. Build panels
    print(f"\n[3/4] 构建面板 ({len(FACTOR_DEFS)} 因子)...")
    price_panel, returns_panel, factor_panels = build_panels(all_data)
    print(f"  日期范围: {price_panel.index[0].strftime('%Y-%m-%d')}"
          f" ~ {price_panel.index[-1].strftime('%Y-%m-%d')}"
          f" ({len(price_panel)} 交易日, {len(price_panel.columns)} 股票)")

    # 每月可用股票数
    test_dates = monthly_ends(price_panel.index, args.start, args.end)
    if test_dates:
        sample = [price_panel.loc[d].notna().sum() for d in test_dates[::6]]
        print(f"  月均可用股票: ~{int(np.mean(sample))}")

    # 4. Grid search
    print(f"\n[4/4] 暴力搜索...")
    ckpt = os.path.join(args.output_dir, "checkpoint.json")
    results = grid_search(price_panel, returns_panel, factor_panels,
                          args.start, args.end, ckpt, args.output_dir)

    report(results)
    save_results(results, args.output_dir)


if __name__ == "__main__":
    main()
