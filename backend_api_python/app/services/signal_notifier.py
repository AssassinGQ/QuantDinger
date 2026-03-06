"""
Strategy signal notification service.

This module implements per-strategy notification channels based on the frontend schema:

notification_config = {
  "channels": ["browser", "email", "phone", "telegram", "discord", "webhook"],
  "targets": {
    "email": "foo@example.com",
    "phone": "+15551234567",
    "telegram": "12345678 or @username",
    "discord": "https://discord.com/api/webhooks/...",
    "webhook": "https://example.com/webhook"
  }
}
"""

from __future__ import annotations

import html
import hmac
import hashlib
import json
import os
import smtplib
import time
import traceback
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any, Dict, List, Optional, Tuple

import requests

from app.utils.db import get_db_connection
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(x).strip() for x in value if str(x).strip()]
    s = str(value).strip()
    if not s:
        return []
    # Allow comma-separated inputs.
    if "," in s:
        return [x.strip() for x in s.split(",") if x.strip()]
    return [s]


def _safe_json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            obj = json.loads(value)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


def _signal_meta(signal_type: str) -> Dict[str, str]:
    st = (signal_type or "").strip().lower()
    action = "signal"
    if st.startswith("open_"):
        action = "open"
    elif st.startswith("add_"):
        action = "add"
    elif st.startswith("close_"):
        action = "close"
    elif st.startswith("reduce_"):
        action = "reduce"

    side = "long" if "long" in st else ("short" if "short" in st else "")
    return {"action": action, "side": side, "type": st}


def _fmt_float(value: Any, *, max_decimals: int = 10) -> str:
    try:
        v = float(value or 0.0)
    except Exception:
        v = 0.0
    s = f"{v:.{int(max_decimals)}f}"
    s = s.rstrip("0").rstrip(".")
    return s or "0"


class SignalNotifier:
    """
    Notify signal events across channels.

    通知配置说明:
    - 用户在个人中心配置自己的通知设置（telegram_bot_token, telegram_chat_id, email 等）
    - 创建策略/监控时，系统自动使用用户配置的通知目标

    公共服务配置（管理员在系统设置中配置）:
    - SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_USE_TLS
      (邮件服务，所有用户共用)
    - TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
      (短信服务，所有用户共用)

    可选的环境变量:
    - SIGNAL_NOTIFY_TIMEOUT_SEC: HTTP timeout (default: 6)
    """

    def __init__(self) -> None:
        try:
            self.timeout_sec = float(os.getenv("SIGNAL_NOTIFY_TIMEOUT_SEC") or "6")
        except Exception:
            self.timeout_sec = 6.0

        # 公共 SMTP 配置（管理员在系统设置中配置）
        self.smtp_host = (os.getenv("SMTP_HOST") or "").strip()
        try:
            self.smtp_port = int(os.getenv("SMTP_PORT") or "587")
        except Exception:
            self.smtp_port = 587
        self.smtp_user = (os.getenv("SMTP_USER") or "").strip()
        self.smtp_password = (os.getenv("SMTP_PASSWORD") or "").strip()
        self.smtp_from = (os.getenv("SMTP_FROM") or self.smtp_user or "").strip()
        self.smtp_use_tls = (os.getenv("SMTP_USE_TLS") or "true").strip().lower() == "true"
        # Some providers require implicit SSL (port 465). Support it via SMTP_USE_SSL.
        self.smtp_use_ssl = (os.getenv("SMTP_USE_SSL") or "").strip().lower() == "true"

        self.twilio_sid = (os.getenv("TWILIO_ACCOUNT_SID") or "").strip()
        self.twilio_token = (os.getenv("TWILIO_AUTH_TOKEN") or "").strip()
        self.twilio_from = (os.getenv("TWILIO_FROM_NUMBER") or "").strip()

    def notify_signal(
        self,
        *,
        strategy_id: int,
        strategy_name: str,
        symbol: str,
        signal_type: str,
        price: float = 0.0,
        stake_amount: float = 0.0,
        direction: str = "long",
        notification_config: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        cfg = _safe_json(notification_config or {})
        channels = _as_list(cfg.get("channels"))
        if not channels:
            channels = ["browser"]

        targets = _safe_json(cfg.get("targets") or {})
        extra = extra if isinstance(extra, dict) else {}

        payload = self._build_payload(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            symbol=symbol,
            signal_type=signal_type,
            price=price,
            stake_amount=stake_amount,
            direction=direction,
            extra=extra,
        )
        rendered = self._render_messages(payload)
        title = rendered.get("title") or ""
        message_plain = rendered.get("plain") or ""

        results: Dict[str, Dict[str, Any]] = {}
        for ch in channels:
            c = (ch or "").strip().lower()
            if not c:
                continue
            try:
                if c == "browser":
                    ok, err = self._notify_browser(
                        strategy_id=strategy_id,
                        symbol=symbol,
                        signal_type=signal_type,
                        channels=channels,
                        title=title,
                        message=message_plain,
                        payload=payload,
                    )
                elif c == "webhook":
                    url = (targets.get("webhook") or "").strip()
                    ok, err = self._notify_webhook(
                        url=url,
                        payload=payload,
                        headers_override=(targets.get("webhook_headers") or targets.get("webhookHeaders") or None),
                        token_override=(targets.get("webhook_token") or targets.get("webhookToken") or None),
                        signing_secret_override=(
                            targets.get("webhook_signing_secret")
                            or targets.get("webhookSigningSecret")
                            or None
                        ),
                    )
                elif c == "discord":
                    url = (targets.get("discord") or "").strip()
                    ok, err = self._notify_discord(url=url, payload=payload, fallback_text=message_plain)
                elif c == "telegram":
                    chat_id = (targets.get("telegram") or "").strip()
                    # User's token takes priority, then falls back to env TELEGRAM_BOT_TOKEN.
                    token_override = ""
                    try:
                        token_override = str(
                            targets.get("telegram_bot_token")
                            or targets.get("telegram_token")
                            or cfg.get("telegram_bot_token")
                            or cfg.get("telegram_token")
                            or ""
                        ).strip()
                    except Exception:
                        token_override = ""
                    ok, err = self._notify_telegram(
                        chat_id=chat_id,
                        text=rendered.get("telegram_html") or message_plain,
                        token_override=token_override,
                        parse_mode="HTML",
                    )
                elif c == "email":
                    to_email = (targets.get("email") or "").strip()
                    ok, err = self._notify_email(
                        to_email=to_email,
                        subject=title,
                        body_text=message_plain,
                        body_html=rendered.get("email_html") or "",
                    )
                elif c == "phone":
                    to_phone = (targets.get("phone") or "").strip()
                    ok, err = self._notify_phone(to_phone=to_phone, body=message_plain)
                else:
                    ok, err = False, f"unsupported_channel:{c}"
            except Exception as e:
                ok, err = False, str(e)

            results[c] = {"ok": bool(ok), "error": (err or "")}
            if not ok and c in ("webhook", "discord"):
                # Keep logs high-signal and avoid leaking full URLs (webhook URLs contain secrets).
                logger.info(
                    f"notify failed: channel={c} strategy_id={strategy_id} symbol={symbol} signal={signal_type} err={err}"
                )

        return results

    def _build_payload(
        self,
        *,
        strategy_id: int,
        strategy_name: str,
        symbol: str,
        signal_type: str,
        price: float,
        stake_amount: float,
        direction: str,
        extra: Dict[str, Any],
    ) -> Dict[str, Any]:
        now = int(time.time())
        iso = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()
        meta = _signal_meta(signal_type)

        pending_id = None
        try:
            pending_id = int((extra or {}).get("pending_order_id") or 0) or None
        except Exception:
            pending_id = None

        ex = extra or {}

        return {
            "event": "qd.signal",
            "version": 1,
            "timestamp": now,
            "timestamp_iso": iso,
            "strategy": {
                "id": int(strategy_id),
                "name": str(strategy_name or ""),
            },
            "instrument": {
                "symbol": str(symbol or ""),
                "display_name": str(ex.get("symbol_name") or ""),
            },
            "signal": {
                "type": meta.get("type") or str(signal_type or ""),
                "action": meta.get("action") or "signal",
                "side": meta.get("side") or "",
                "direction": str(direction or ""),
            },
            "order": {
                "ref_price": float(price or 0.0),
                "stake_amount": float(stake_amount or 0.0),
            },
            "execution": {
                "status": str(ex.get("status") or ""),
                "error": str(ex.get("error") or ""),
                "exchange_id": str(ex.get("exchange_id") or ""),
                "exchange_order_id": str(ex.get("exchange_order_id") or ""),
                "market_category": str(ex.get("market_category") or ""),
                "market_type": str(ex.get("market_type") or ""),
                "filled_price": float(ex.get("filled_price") or 0.0),
                "filled_amount": float(ex.get("filled_amount") or 0.0),
                "profit": ex.get("profit"),
                "entry_price": float(ex.get("entry_price") or 0.0),
                "position_opened_at": str(ex.get("position_opened_at") or ""),
            },
            "trace": {
                "pending_order_id": pending_id,
                "mode": str(ex.get("mode") or ""),
            },
            "extra": extra or {},
        }

    @staticmethod
    def _extract_render_ctx(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Extract all fields needed by _render_messages into a flat dict."""
        strategy = (payload or {}).get("strategy") or {}
        instrument = (payload or {}).get("instrument") or {}
        sig = (payload or {}).get("signal") or {}
        order = (payload or {}).get("order") or {}
        trace = (payload or {}).get("trace") or {}
        execution = (payload or {}).get("execution") or {}

        symbol = str(instrument.get("symbol") or "")
        display_name = str(instrument.get("display_name") or "")
        action = str(sig.get("action") or "").upper()
        exec_status = str(execution.get("status") or "")
        mode = str(trace.get("mode") or "")
        is_close = action in ("CLOSE", "REDUCE")

        filled_price = float(execution.get("filled_price") or 0.0)
        filled_amount = float(execution.get("filled_amount") or 0.0)
        entry_price = float(execution.get("entry_price") or 0.0)

        raw_profit = execution.get("profit")
        profit = None
        if raw_profit is not None:
            try:
                profit = float(raw_profit)
            except (TypeError, ValueError):
                pass

        status_tag = f" [{exec_status.upper()}]" if exec_status else ""
        symbol_label = f"{symbol} ({display_name})" if display_name else symbol
        t_strategy = f"{strategy.get('name') or ''} (#{int(strategy.get('id') or 0)})"

        return {
            "symbol_label": symbol_label,
            "stype": str(sig.get("type") or ""),
            "action": action,
            "side": str(sig.get("side") or "").upper(),
            "is_close": is_close,
            "mode": mode,
            "exec_status": exec_status,
            "exec_error": str(execution.get("error") or ""),
            "exchange_id": str(execution.get("exchange_id") or ""),
            "exchange_order_id": str(execution.get("exchange_order_id") or ""),
            "market_category": str(execution.get("market_category") or ""),
            "filled_price": filled_price,
            "filled_amount": filled_amount,
            "entry_price": entry_price,
            "position_opened_at": str(execution.get("position_opened_at") or ""),
            "profit": profit,
            "title": f"QD {mode.upper() or 'Signal'} | {symbol_label} | {action} {str(sig.get('side') or '').upper()}{status_tag}".strip(),
            "price_s": _fmt_float(order.get("ref_price") or 0.0, max_decimals=10),
            "stake_s": _fmt_float(order.get("stake_amount") or 0.0, max_decimals=12),
            "pending_id": int(trace.get("pending_order_id") or 0) if trace.get("pending_order_id") else 0,
            "ts_iso": str(payload.get("timestamp_iso") or ""),
            "t_strategy": t_strategy,
        }

    @staticmethod
    def _build_optional_rows(ctx: Dict[str, Any]) -> List[Tuple[str, str]]:
        """Build a list of (label, value) for optional fields present in ctx."""
        rows: List[Tuple[str, str]] = []
        # Simple string fields: (label, ctx_key)
        _STR_FIELDS = [
            ("Market", "market_category"), ("Exchange", "exchange_id"), ("Mode", "mode"),
            ("Status", "exec_status"),
        ]
        for label, key in _STR_FIELDS:
            if ctx[key]:
                rows.append((label, ctx[key]))
        # Numeric fill fields
        if ctx["filled_price"] > 0:
            rows.append(("Filled Price", _fmt_float(ctx["filled_price"], max_decimals=10)))
        if ctx["filled_amount"] > 0:
            rows.append(("Filled Amount", _fmt_float(ctx["filled_amount"], max_decimals=12)))
        # Close-specific fields
        if ctx["is_close"]:
            if ctx["entry_price"] > 0:
                rows.append(("Entry Price", _fmt_float(ctx["entry_price"], max_decimals=10)))
            if ctx["profit"] is not None:
                pnl_sign = "+" if ctx["profit"] >= 0 else ""
                rows.append(("P&L", f"{pnl_sign}{_fmt_float(ctx['profit'], max_decimals=4)}"))
            if ctx["position_opened_at"]:
                rows.append(("Position Opened", ctx["position_opened_at"]))
        # Trailing fields
        _TAIL_FIELDS = [("Order ID", "exchange_order_id"), ("Error", "exec_error")]
        for label, key in _TAIL_FIELDS:
            val = ctx[key]
            if val:
                rows.append((label, val[:500] if label == "Error" else val))
        if ctx["pending_id"]:
            rows.append(("PendingOrder", str(int(ctx["pending_id"]))))
        if ctx["ts_iso"]:
            rows.append(("Time (UTC)", ctx["ts_iso"]))
        return rows

    def _render_messages(self, payload: Dict[str, Any]) -> Dict[str, str]:
        ctx = self._extract_render_ctx(payload)
        title = ctx["title"]
        opt_rows = self._build_optional_rows(ctx)

        # -- plain text --
        plain_lines = [
            "QuantDinger Signal",
            f"Strategy: {ctx['t_strategy']}",
            f"Symbol: {ctx['symbol_label']}",
            f"Signal: {ctx['stype']}",
            f"Ref Price: {ctx['price_s']}",
            f"Amount: {ctx['stake_s']}",
        ]
        for label, val in opt_rows:
            plain_lines.append(f"{label}: {val}")

        # -- Telegram (HTML) message --
        telegram_lines = [
            "<b>QuantDinger Signal</b>",
            "",
            f"<b>Strategy</b>: <code>{html.escape(ctx['t_strategy'])}</code>",
            f"<b>Symbol</b>: <code>{html.escape(ctx['symbol_label'])}</code>",
            f"<b>Signal</b>: <code>{html.escape(ctx['stype'])}</code>",
            f"<b>Ref Price</b>: <code>{html.escape(ctx['price_s'])}</code>",
            f"<b>Amount</b>: <code>{html.escape(ctx['stake_s'])}</code>",
        ]
        _STATUS_EMOJI = {"filled": "\u2705", "failed": "\u274c", "deferred": "\u23f3"}
        for label, val in opt_rows:
            v_esc = html.escape(str(val))
            if label == "Status":
                emoji = _STATUS_EMOJI.get(val.lower(), "\u2139\ufe0f")
                telegram_lines.append(f"<b>{label}</b>: {emoji} <code>{v_esc}</code>")
            elif label == "P&L":
                pnl_emoji = "\U0001f4c8" if val.startswith("+") else "\U0001f4c9"
                telegram_lines.append(f"{pnl_emoji} <b>P&amp;L</b>: <code>{v_esc}</code>")
            elif label == "Error":
                telegram_lines.append(f"\n\u26a0\ufe0f <b>Error</b>: <code>{v_esc}</code>")
            else:
                telegram_lines.append(f"<b>{html.escape(label)}</b>: <code>{v_esc}</code>")
        telegram_html = "\n".join(telegram_lines)

        # -- Email (HTML) message --
        email_rows: List[Tuple[str, str]] = [
            ("Strategy", ctx["t_strategy"]),
            ("Symbol", ctx["symbol_label"]),
            ("Signal", ctx["stype"]),
            ("Ref Price", ctx["price_s"]),
            ("Amount", ctx["stake_s"]),
        ] + opt_rows

        email_html = self._build_email_html(
            title_text=title,
            rows=email_rows,
            timestamp_iso=ctx["ts_iso"],
            status=ctx["exec_status"],
        )

        return {
            "title": title,
            "plain": "\n".join(plain_lines),
            "telegram_html": telegram_html,
            "email_html": email_html,
        }

    def _build_email_html(
        self,
        *,
        title_text: str,
        rows: List[Tuple[str, str]],
        timestamp_iso: str = "",
        status: str = "",
    ) -> str:
        def esc(s: Any) -> str:
            return html.escape(str(s or ""))

        _STATUS_COLORS = {
            "filled": ("#0d6e3b", "#dcfce7"),
            "failed": ("#991b1b", "#fee2e2"),
            "deferred": ("#92400e", "#fef3c7"),
        }
        header_bg = "#111827"
        st_lower = (status or "").strip().lower()
        accent_color, _ = _STATUS_COLORS.get(st_lower, (None, None))

        def _render_value(key: str, val: str) -> str:
            k_lower = key.lower()
            v_esc = esc(val)
            if k_lower == "status" and st_lower in _STATUS_COLORS:
                fg, bg = _STATUS_COLORS[st_lower]
                return (
                    f"<span style='display:inline-block;padding:2px 10px;border-radius:4px;"
                    f"background:{bg};color:{fg};font-weight:600;'>{v_esc}</span>"
                )
            if k_lower == "error" and val:
                return (
                    f"<span style='color:#991b1b;background:#fee2e2;padding:2px 8px;"
                    f"border-radius:4px;word-break:break-all;'>{v_esc}</span>"
                )
            if k_lower == "p&l" and val:
                is_positive = val.strip().startswith("+") or (val.strip() and val.strip()[0].isdigit())
                fg = "#0d6e3b" if is_positive else "#991b1b"
                bg = "#dcfce7" if is_positive else "#fee2e2"
                return (
                    f"<span style='display:inline-block;padding:2px 10px;border-radius:4px;"
                    f"background:{bg};color:{fg};font-weight:700;font-size:15px;'>{v_esc}</span>"
                )
            return v_esc

        tr_html = "\n".join(
            [
                (
                    "<tr>"
                    "<td style='padding:10px 12px;border-top:1px solid #eaecef;color:#57606a;width:160px;"
                    "font-size:13px;vertical-align:top;'>"
                    f"{esc(k)}"
                    "</td>"
                    "<td style='padding:10px 12px;border-top:1px solid #eaecef;color:#24292f;"
                    "font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "
                    "\"Liberation Mono\", \"Courier New\", monospace;font-size:14px;'>"
                    f"{_render_value(k, v)}"
                    "</td>"
                    "</tr>"
                )
                for (k, v) in rows
            ]
        )

        return f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f6f8fa;">
    <div style="max-width:640px;margin:0 auto;padding:24px;">
      <div style="background:{header_bg};color:#ffffff;padding:16px 18px;border-radius:12px 12px 0 0;">
        <div style="font-size:16px;letter-spacing:0.2px;font-weight:600;">{esc(title_text)}</div>
        <div style="margin-top:6px;font-size:12px;color:#d1d5db;">{esc(timestamp_iso) if timestamp_iso else ""}</div>
      </div>
      <div style="background:#ffffff;border:1px solid #eaecef;border-top:0;border-radius:0 0 12px 12px;overflow:hidden;">
        <table cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;">
          {tr_html}
        </table>
        <div style="padding:14px 16px;color:#6e7781;font-size:12px;border-top:1px solid #eaecef;">
          Generated by QuantDinger
        </div>
      </div>
    </div>
  </body>
</html>
"""

    def _notify_browser(
        self,
        *,
        strategy_id: int,
        symbol: str,
        signal_type: str,
        channels: List[str],
        title: str,
        message: str,
        payload: Dict[str, Any],
        user_id: int = None,
    ) -> Tuple[bool, str]:
        try:
            now = int(time.time())
            # Get user_id from strategy if not provided
            if user_id is None:
                try:
                    with get_db_connection() as db:
                        cur = db.cursor()
                        cur.execute("SELECT user_id FROM qd_strategies_trading WHERE id = ?", (strategy_id,))
                        row = cur.fetchone()
                        cur.close()
                    user_id = int((row or {}).get('user_id') or 1)
                except Exception:
                    user_id = 1
            with get_db_connection() as db:
                cur = db.cursor()
                cur.execute(
                    """
                    INSERT INTO qd_strategy_notifications
                    (user_id, strategy_id, symbol, signal_type, channels, title, message, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, NOW())
                    """,
                    (
                        int(user_id),
                        int(strategy_id),
                        str(symbol or ""),
                        str(signal_type or ""),
                        ",".join([str(c) for c in (channels or [])]),
                        str(title or ""),
                        str(message or ""),
                        json.dumps(payload or {}, ensure_ascii=False),
                    ),
                )
                db.commit()
                cur.close()
            return True, ""
        except Exception as e:
            logger.warning(f"browser notify persist failed: {e}")
            logger.error('browser.error\n%s', traceback.format_exc())
            return False, str(e)

    def _notify_webhook(
        self,
        *,
        url: str,
        payload: Dict[str, Any],
        headers_override: Any = None,
        token_override: Any = None,
        signing_secret_override: Any = None,
    ) -> Tuple[bool, str]:
        """
        Generic webhook delivery.

        用户在个人中心配置：
        - webhook_url: Webhook 地址
        - webhook_token: Bearer Token（可选）

        支持功能：
        - 自定义 headers: notification_config.targets.webhook_headers
        - Bearer Token: notification_config.targets.webhook_token
        - 签名验证: notification_config.targets.webhook_signing_secret
        - 自动重试: 429/5xx 时重试一次
        """
        if not url:
            return False, "missing_webhook_url"
        if not (str(url).startswith("http://") or str(url).startswith("https://")):
            return False, "invalid_webhook_url"

        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": "QuantDinger/1.0 (+https://www.quantdinger.com)",
        }

        # Per-strategy header overrides (optional)
        wh = headers_override
        if isinstance(wh, str) and wh.strip():
            try:
                obj = json.loads(wh)
                wh = obj if isinstance(obj, dict) else None
            except Exception:
                wh = None
        if isinstance(wh, dict):
            for k, v in wh.items():
                kk = str(k or "").strip()
                if not kk:
                    continue
                headers[kk] = str(v if v is not None else "")

        # Auth (user's token from notification_config.targets.webhook_token)
        tok = str(token_override or "").strip()
        if tok and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {tok}"

        # Optional signing secret (per-strategy override, else env)
        signing_secret = str(signing_secret_override or "").strip() or (os.getenv("SIGNAL_WEBHOOK_SIGNING_SECRET") or "").strip()
        if signing_secret:
            try:
                ts = str(int(time.time()))
                body = json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                sig_base = (ts + ".").encode("utf-8") + body
                sig = hmac.new(signing_secret.encode("utf-8"), sig_base, hashlib.sha256).hexdigest()
                headers["X-QD-Timestamp"] = ts
                headers["X-QD-Signature"] = sig
                # Send raw bytes so signature matches what we sign.
                def _post_once(timeout: float) -> requests.Response:
                    return requests.post(url, data=body, headers=headers, timeout=timeout)
            except Exception as e:
                return False, f"webhook_signing_failed:{e}"
        else:
            def _post_once(timeout: float) -> requests.Response:
                return requests.post(url, json=payload, headers=headers, timeout=timeout)

        # Post with minimal retry on 429/5xx
        try:
            resp = _post_once(self.timeout_sec)
            if 200 <= resp.status_code < 300:
                return True, ""
            if resp.status_code in (429, 500, 502, 503, 504):
                try:
                    time.sleep(1.0)
                except Exception:
                    pass
                resp2 = _post_once(self.timeout_sec)
                if 200 <= resp2.status_code < 300:
                    return True, ""
                return False, f"http_{resp2.status_code}:{(resp2.text or '')[:300]}"
            return False, f"http_{resp.status_code}:{(resp.text or '')[:300]}"
        except Exception as e:
            logger.error('webhook.error\n%s', traceback.format_exc())
            return False, str(e)

    def _notify_discord(self, *, url: str, payload: Dict[str, Any], fallback_text: str) -> Tuple[bool, str]:
        if not url:
            return False, "missing_discord_webhook_url"
        if not (str(url).startswith("http://") or str(url).startswith("https://")):
            return False, "invalid_discord_webhook_url"

        strategy = (payload or {}).get("strategy") or {}
        instrument = (payload or {}).get("instrument") or {}
        sig = (payload or {}).get("signal") or {}
        order = (payload or {}).get("order") or {}
        trace = (payload or {}).get("trace") or {}

        action = str(sig.get("action") or "").lower()
        color = 0x3498DB
        if action in ("open", "add"):
            color = 0x2ECC71
        if action in ("close", "reduce"):
            color = 0xE74C3C

        embed: Dict[str, Any] = {
            "title": "QuantDinger Signal",
            "color": int(color),
            "fields": [
                {"name": "Strategy", "value": f"{strategy.get('name') or ''} (#{int(strategy.get('id') or 0)})", "inline": True},
                {"name": "Symbol", "value": str(instrument.get("symbol") or ""), "inline": True},
                {"name": "Signal", "value": str(sig.get("type") or ""), "inline": False},
                {"name": "Price", "value": str(float(order.get('ref_price') or 0.0)), "inline": True},
                {"name": "Stake", "value": str(float(order.get('stake_amount') or 0.0)), "inline": True},
            ],
        }
        if payload.get("timestamp_iso"):
            embed["timestamp"] = str(payload.get("timestamp_iso") or "")
        if trace.get("pending_order_id"):
            embed["footer"] = {"text": f"pending_order_id={int(trace.get('pending_order_id'))}"}
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "QuantDinger/1.0 (+https://www.quantdinger.com)",
        }

        def _post(payload_json: Dict[str, Any]) -> requests.Response:
            return requests.post(url, json=payload_json, headers=headers, timeout=self.timeout_sec)

        try:
            resp = _post({"content": "", "embeds": [embed]})
            if 200 <= resp.status_code < 300:
                return True, ""

            # Rate limit: retry once if Discord asks us to.
            if resp.status_code == 429:
                try:
                    data = resp.json() if resp is not None else {}
                    retry_after = float((data or {}).get("retry_after") or 1.0)
                    time.sleep(min(max(retry_after, 0.5), 3.0))
                except Exception:
                    try:
                        time.sleep(1.0)
                    except Exception:
                        pass
                resp_retry = _post({"content": "", "embeds": [embed]})
                if 200 <= resp_retry.status_code < 300:
                    return True, ""
                resp = resp_retry

            # Fallback: plain text (some servers reject embeds)
            try:
                resp2 = _post({"content": str(fallback_text or "")[:1900]})
                if 200 <= resp2.status_code < 300:
                    return True, ""
                # If fallback also fails, return the original error (more useful than fallback sometimes).
            except Exception:
                pass
            return False, f"http_{resp.status_code}:{(resp.text or '')[:300]}"
        except Exception as e:
            logger.error('discord.error\n%s', traceback.format_exc())
            return False, str(e)

    def _notify_telegram(
        self,
        *,
        chat_id: str,
        text: str,
        token_override: str = "",
        parse_mode: str = "",
    ) -> Tuple[bool, str]:
        # 用户必须在个人中心配置自己的 telegram_bot_token
        token = (token_override or "").strip()
        if not token:
            return False, "missing_telegram_bot_token (请在个人中心配置 Telegram Bot Token)"
        if not chat_id:
            return False, "missing_telegram_chat_id"
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            data: Dict[str, Any] = {
                "chat_id": chat_id,
                "text": str(text or "")[:3900],
                "disable_web_page_preview": True,
            }
            if (parse_mode or "").strip():
                data["parse_mode"] = str(parse_mode).strip()
            resp = requests.post(
                url,
                data=data,
                timeout=self.timeout_sec,
            )
            if 200 <= resp.status_code < 300:
                return True, ""
            return False, f"http_{resp.status_code}:{(resp.text or '')[:300]}"
        except Exception as e:
            logger.error('telegram.error\n%s', traceback.format_exc())
            return False, str(e)

    def _notify_email(self, *, to_email: str, subject: str, body_text: str, body_html: str = "") -> Tuple[bool, str]:
        if not to_email:
            return False, "missing_email_target"
        if not self.smtp_host:
            return False, "missing_SMTP_HOST"
        if not self.smtp_from:
            return False, "missing_SMTP_FROM"

        msg = EmailMessage()
        msg["From"] = self.smtp_from
        msg["To"] = to_email
        msg["Subject"] = str(subject or "Signal")
        msg.set_content(str(body_text or ""))
        if (body_html or "").strip():
            msg.add_alternative(str(body_html or ""), subtype="html")

        try:
            # Heuristic: if port is 465 and SMTP_USE_SSL is not explicitly set, assume SSL.
            use_ssl = bool(self.smtp_use_ssl) or int(self.smtp_port or 0) == 465
            if use_ssl:
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=self.timeout_sec) as server:
                    server.ehlo()
                    if self.smtp_user and self.smtp_password:
                        server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=self.timeout_sec) as server:
                    server.ehlo()
                    if self.smtp_use_tls:
                        server.starttls()
                        server.ehlo()
                    if self.smtp_user and self.smtp_password:
                        server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)
            return True, ""
        except Exception as e:
            logger.error('email.error\n%s', traceback.format_exc())
            return False, str(e)

    def _notify_phone(self, *, to_phone: str, body: str) -> Tuple[bool, str]:
        # Optional provider: Twilio via REST (no extra dependency).
        if not to_phone:
            return False, "missing_phone_target"
        if not (self.twilio_sid and self.twilio_token and self.twilio_from):
            return False, "missing_TWILIO_config"
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_sid}/Messages.json"
        data = {"To": to_phone, "From": self.twilio_from, "Body": str(body or "")[:1500]}
        try:
            resp = requests.post(url, data=data, auth=(self.twilio_sid, self.twilio_token), timeout=self.timeout_sec)
            if 200 <= resp.status_code < 300:
                return True, ""
            return False, f"http_{resp.status_code}:{(resp.text or '')[:300]}"
        except Exception as e:
            logger.error('phone.error\n%s', traceback.format_exc())
            return False, str(e)


