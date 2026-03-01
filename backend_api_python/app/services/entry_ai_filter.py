"""
开仓 AI 过滤：基于 FastAnalysisService 对 open_long/open_short 信号进行过滤。
便于替换或扩展 AI 逻辑。
"""
import logging
from typing import Any, Dict, Optional, Tuple

from app.services.fast_analysis import get_fast_analysis_service

logger = logging.getLogger(__name__)

def is_entry_ai_filter_enabled(
    *,
    ai_model_config: Optional[Dict[str, Any]],
    trading_config: Optional[Dict[str, Any]],
) -> bool:
    """
    Detect whether the strategy enabled 'AI filter on entry (open positions only)'.
    """
    amc = ai_model_config if isinstance(ai_model_config, dict) else {}
    tc = trading_config if isinstance(trading_config, dict) else {}

    candidates = [
        amc.get("entry_ai_filter_enabled"),
        amc.get("entryAiFilterEnabled"),
        amc.get("ai_filter_enabled"),
        amc.get("aiFilterEnabled"),
        amc.get("enable_ai_filter"),
        amc.get("enableAiFilter"),
        tc.get("entry_ai_filter_enabled"),
        tc.get("ai_filter_enabled"),
        tc.get("enable_ai_filter"),
        tc.get("enableAiFilter"),
    ]
    for v in candidates:
        if v is None:
            continue
        if isinstance(v, bool):
            return bool(v)
        s = str(v).strip().lower()
        if s in ("1", "true", "yes", "y", "on", "enabled"):
            return True
        if s in ("0", "false", "no", "n", "off", "disabled"):
            return False
    return False

def _get_analysis_params(
    ai_model_config: Dict[str, Any],
    trading_config: Dict[str, Any],
) -> Tuple[str, Optional[str], str]:
    """Extract market, model, and language from configs."""
    market = str(
        ai_model_config.get("market") or ai_model_config.get("analysis_market") or "Crypto"
    ).strip() or "Crypto"

    model = (
        ai_model_config.get("model") or ai_model_config.get("openrouter_model")
        or ai_model_config.get("openrouterModel")
    )
    model = str(model).strip() if model else None

    language = (
        ai_model_config.get("language") or ai_model_config.get("lang")
        or trading_config.get("language") or "zh-CN"
    )
    language = str(language or "zh-CN")

    return market, model, language

def entry_ai_filter_allows(
    *,
    symbol: str,
    signal_type: str,
    ai_model_config: Optional[Dict[str, Any]],
    trading_config: Optional[Dict[str, Any]],
) -> Tuple[bool, Dict[str, Any]]:
    """
    Run internal AI analysis and decide whether an entry signal is allowed.

    Returns:
      (allowed, info)
      - allowed: True -> proceed; False -> hold (reject open)
      - info: {ai_decision, reason, analysis_error?}
    """
    amc = ai_model_config if isinstance(ai_model_config, dict) else {}
    tc = trading_config if isinstance(trading_config, dict) else {}

    market, model, language = _get_analysis_params(amc, tc)

    try:
        service = get_fast_analysis_service()
        result = service.analyze(market, symbol, language, model=model)

        if isinstance(result, dict) and result.get("error"):
            return False, {
                "ai_decision": "",
                "reason": "analysis_error",
                "analysis_error": str(result.get("error") or ""),
            }

        ai_dec = str(result.get("decision", "")).strip().upper()
        if not ai_dec or ai_dec not in ("BUY", "SELL", "HOLD"):
            return False, {"ai_decision": ai_dec, "reason": "missing_ai_decision"}

        expected = "BUY" if signal_type == "open_long" else "SELL"
        info = {
            "ai_decision": ai_dec,
            "confidence": result.get("confidence", 50),
            "summary": result.get("summary", "")
        }
        if ai_dec == expected:
            return True, {**info, "reason": "match"}
        if ai_dec == "HOLD":
            return False, {**info, "reason": "ai_hold"}
        return False, {**info, "reason": "direction_mismatch"}
    except (
        ValueError, TypeError, KeyError, AttributeError,
        RuntimeError, ConnectionError, OSError
    ) as e:
        logger.error("AI filter analysis failed: %s", e)
        return False, {
            "ai_decision": "",
            "reason": "analysis_exception",
            "analysis_error": str(e),
        }

def extract_ai_trade_decision(analysis_result: Any) -> str:
    """
    Normalize AI analysis output into one of: BUY / SELL / HOLD / "".
    """
    if not isinstance(analysis_result, dict):
        return ""

    def _pick(*paths: str) -> str:
        for p in paths:
            cur: Any = analysis_result
            ok = True
            for k in p.split("."):
                if not isinstance(cur, dict):
                    ok = False
                    break
                cur = cur.get(k)
            if ok and cur is not None:
                s = str(cur).strip()
                if s:
                    return s
        return ""

    raw = _pick(
        "final_decision.decision",
        "trader_decision.decision",
        "decision",
        "final.decision",
    )
    s = raw.strip().upper()
    if not s:
        return ""

    if "BUY" in s or s == "LONG" or "LONG" in s:
        return "BUY"
    if "SELL" in s or s == "SHORT" or "SHORT" in s:
        return "SELL"
    if "HOLD" in s or "WAIT" in s or "NEUTRAL" in s:
        return "HOLD"
    return s if s in ("BUY", "SELL", "HOLD") else ""
