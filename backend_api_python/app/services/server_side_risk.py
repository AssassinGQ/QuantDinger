"""
服务端风控：止损、止盈、追踪止盈。
由 trading_config 驱动，不依赖指标脚本。
供 TradingExecutor 调用。
"""
import time
from typing import Any, Dict, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)


def to_ratio(v: Any, default: float = 0.0) -> float:
    """
    Convert a percent-like value into ratio in [0, 1].
    Accepts both 0~1 and 0~100 inputs.
    """
    try:
        x = float(v if v is not None else default)
    except (ValueError, TypeError):
        x = float(default or 0.0)
    if x > 1.0:
        x = x / 100.0
    if x < 0:
        x = 0.0
    if x > 1.0:
        x = 1.0
    return float(x)


def check_stop_loss_signal(
    data_handler: Any,
    strategy_id: int,
    symbol: str,
    current_price: float,
    market_type: str,
    leverage: float,
    trading_config: Dict[str, Any],
    timeframe_seconds: int,
) -> Optional[Dict[str, Any]]:
    """
    服务端兜底止损：当价格穿透止损线时，直接生成 close_long/close_short 信号。
    """
    try:
        if trading_config is None:
            return None

        enabled = trading_config.get('enable_server_side_stop_loss', True)
        if str(enabled).lower() in ['0', 'false', 'no', 'off']:
            return None

        current_positions = data_handler.get_current_positions(strategy_id, symbol)
        if not current_positions:
            return None

        pos = current_positions[0]
        side = pos.get('side')
        if side not in ['long', 'short']:
            return None

        entry_price = float(pos.get('entry_price', 0) or 0)
        if entry_price <= 0 or current_price <= 0:
            return None

        sl_cfg = trading_config.get('stop_loss_pct', 0)
        sl = 0.0
        try:
            sl_cfg = float(sl_cfg or 0)
            if sl_cfg > 1:
                sl = sl_cfg / 100.0
            else:
                sl = sl_cfg
        except Exception:
            sl = 0.0

        if sl <= 0:
            return None

        lev = max(1.0, float(leverage or 1.0))
        sl = sl / lev

        now_ts = int(time.time())
        tf = int(timeframe_seconds or 60)
        candle_ts = int(now_ts // tf) * tf

        if side == 'long':
            stop_line = entry_price * (1 - sl)
            if current_price <= stop_line:
                return {
                    'type': 'close_long',
                    'trigger_price': 0,
                    'position_size': 0,
                    'timestamp': candle_ts,
                    'reason': 'server_stop_loss',
                    'stop_loss_price': stop_line,
                }
        elif side == 'short':
            stop_line = entry_price * (1 + sl)
            if current_price >= stop_line:
                return {
                    'type': 'close_short',
                    'trigger_price': 0,
                    'position_size': 0,
                    'timestamp': candle_ts,
                    'reason': 'server_stop_loss',
                    'stop_loss_price': stop_line,
                }

        return None
    except Exception as e:
        logger.warning(
            "Strategy %s server-side stop-loss check failed: %s",
            strategy_id,
            e,
        )
        return None


def check_take_profit_or_trailing_signal(
    data_handler: Any,
    strategy_id: int,
    symbol: str,
    current_price: float,
    market_type: str,
    leverage: float,
    trading_config: Dict[str, Any],
    timeframe_seconds: int,
) -> Optional[Dict[str, Any]]:
    """
    Server-side exits: fixed take-profit 与 trailing stop.
    """
    try:
        if not trading_config:
            return None

        current_positions = data_handler.get_current_positions(strategy_id, symbol)
        if not current_positions:
            return None

        pos = current_positions[0]
        side = (pos.get('side') or '').strip().lower()
        if side not in ['long', 'short']:
            return None

        entry_price = float(pos.get('entry_price', 0) or 0)
        if entry_price <= 0 or current_price <= 0:
            return None

        lev = max(1.0, float(leverage or 1.0))

        tp = to_ratio(trading_config.get('take_profit_pct'))
        trailing_enabled = bool(trading_config.get('trailing_enabled'))
        trailing_pct = to_ratio(trading_config.get('trailing_stop_pct'))
        trailing_act = to_ratio(trading_config.get('trailing_activation_pct'))

        tp_eff = (tp / lev) if tp > 0 else 0.0
        trailing_pct_eff = (trailing_pct / lev) if trailing_pct > 0 else 0.0
        trailing_act_eff = (trailing_act / lev) if trailing_act > 0 else 0.0

        if trailing_enabled and trailing_pct_eff > 0:
            tp_eff = 0.0
            if trailing_act_eff <= 0 and tp > 0:
                trailing_act_eff = tp / lev

        now_ts = int(time.time())
        tf = int(timeframe_seconds or 60)
        candle_ts = int(now_ts // tf) * tf

        try:
            hp = float(pos.get('highest_price') or 0.0)
        except Exception:
            hp = 0.0
        try:
            lp = float(pos.get('lowest_price') or 0.0)
        except Exception:
            lp = 0.0

        if hp <= 0:
            hp = entry_price
        hp = max(hp, float(current_price))

        if lp <= 0:
            lp = entry_price
        lp = min(lp, float(current_price))

        try:
            data_handler.update_position(
                strategy_id=strategy_id,
                symbol=pos.get('symbol') or symbol,
                side=side,
                size=float(pos.get('size') or 0.0),
                entry_price=entry_price,
                current_price=float(current_price),
                highest_price=hp,
                lowest_price=lp,
            )
        except Exception:
            pass

        if trailing_enabled and trailing_pct_eff > 0:
            if side == 'long':
                active = True
                if trailing_act_eff > 0:
                    active = hp >= entry_price * (1 + trailing_act_eff)
                if active:
                    stop_line = hp * (1 - trailing_pct_eff)
                    if current_price <= stop_line:
                        return {
                            'type': 'close_long',
                            'trigger_price': 0,
                            'position_size': 0,
                            'timestamp': candle_ts,
                            'reason': 'server_trailing_stop',
                            'trailing_stop_price': stop_line,
                            'highest_price': hp,
                        }
            else:
                active = True
                if trailing_act_eff > 0:
                    active = lp <= entry_price * (1 - trailing_act_eff)
                if active:
                    stop_line = lp * (1 + trailing_pct_eff)
                    if current_price >= stop_line:
                        return {
                            'type': 'close_short',
                            'trigger_price': 0,
                            'position_size': 0,
                            'timestamp': candle_ts,
                            'reason': 'server_trailing_stop',
                            'trailing_stop_price': stop_line,
                            'lowest_price': lp,
                        }

        if tp_eff > 0:
            if side == 'long':
                tp_line = entry_price * (1 + tp_eff)
                if current_price >= tp_line:
                    return {
                        'type': 'close_long',
                        'trigger_price': 0,
                        'position_size': 0,
                        'timestamp': candle_ts,
                        'reason': 'server_take_profit',
                        'take_profit_price': tp_line,
                    }
            else:
                tp_line = entry_price * (1 - tp_eff)
                if current_price <= tp_line:
                    return {
                        'type': 'close_short',
                        'trigger_price': 0,
                        'position_size': 0,
                        'timestamp': candle_ts,
                        'reason': 'server_take_profit',
                        'take_profit_price': tp_line,
                    }

        return None
    except Exception:
        return None
