#!/usr/bin/env python3
"""
IBKR Commission Test Script

验证 commissionReportEvent 的回调时序和参数，定位佣金为零的根因。

测试内容：
1. commissionReportEvent 是否真的被触发
2. 触发时 report.commission 的值
3. 事件触发顺序：orderStatus vs execDetails vs commissionReport
4. commissionReport 触发时 order context 是否仍然存在（竞争条件检测）

用法（在 SSH 容器内执行）：
  python3 /path/to/ibkr_commission_test.py [--place-order]

  不带 --place-order：只监听历史成交的 commission 回调（安全，不下单）
  带 --place-order：下一笔小额市价单来触发完整流程
"""
import asyncio
import os
import sys
import time
import logging
from datetime import datetime
from collections import OrderedDict

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("commission_test")

IBKR_HOST = os.environ.get("IBKR_HOST", "ib-gateway")
IBKR_PORT = int(os.environ.get("IBKR_PORT", "4004"))
IBKR_ACCOUNT = os.environ.get("IBKR_ACCOUNT", "")


class EventTimeline:
    """Record IB events in order to detect race conditions."""

    def __init__(self):
        self.events = []

    def record(self, event_name: str, order_id: int, details: dict):
        ts = time.monotonic()
        self.events.append({
            "ts": ts,
            "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "event": event_name,
            "order_id": order_id,
            **details,
        })
        logger.info("[EVENT] %-25s orderId=%-6s %s", event_name, order_id, details)

    def print_summary(self):
        logger.info("=" * 70)
        logger.info("EVENT TIMELINE SUMMARY")
        logger.info("=" * 70)
        if not self.events:
            logger.warning("  No events recorded!")
            return

        by_order = OrderedDict()
        for e in self.events:
            oid = e["order_id"]
            by_order.setdefault(oid, []).append(e)

        for oid, evts in by_order.items():
            logger.info("  Order %s:", oid)
            t0 = evts[0]["ts"]
            for e in evts:
                delta_ms = (e["ts"] - t0) * 1000
                logger.info(
                    "    +%7.1fms  %-25s %s",
                    delta_ms,
                    e["event"],
                    {k: v for k, v in e.items() if k not in ("ts", "time", "event", "order_id")},
                )


timeline = EventTimeline()
simulated_contexts = {}


def on_order_status(trade):
    oid = trade.order.orderId
    status = trade.orderStatus.status
    filled = float(trade.orderStatus.filled or 0)
    avg_price = float(trade.orderStatus.avgFillPrice or 0)

    timeline.record("orderStatus", oid, {
        "status": status,
        "filled": filled,
        "avgPrice": avg_price,
    })

    if status == "Filled" and filled > 0:
        ctx = simulated_contexts.get(oid)
        if ctx:
            logger.warning(
                "  [RACE CHECK] orderStatus=Filled → about to pop context for orderId=%s. "
                "If commissionReport arrives AFTER this, ctx will be None!",
                oid,
            )
            simulated_contexts.pop(oid, None)
            timeline.record("context_removed_by_orderStatus", oid, {})


def on_exec_details(trade, fill):
    oid = trade.order.orderId
    timeline.record("execDetails", oid, {
        "execId": fill.execution.execId,
        "side": fill.execution.side,
        "shares": fill.execution.shares,
        "price": fill.execution.price,
    })


def on_commission_report(trade, fill, report):
    oid = trade.order.orderId
    commission = float(report.commission or 0)
    currency = report.currency or ""
    realized_pnl = float(report.realizedPNL or 0)
    exec_id = fill.execution.execId

    ctx = simulated_contexts.get(oid)
    ctx_exists = ctx is not None

    timeline.record("commissionReport", oid, {
        "commission": commission,
        "currency": currency,
        "realizedPNL": realized_pnl,
        "execId": exec_id,
        "context_still_exists": ctx_exists,
    })

    if not ctx_exists:
        logger.error(
            "  *** BUG CONFIRMED: commissionReport fired AFTER context was removed! "
            "orderId=%s commission=%.4f — this commission will be LOST ***",
            oid, commission,
        )
    elif commission > 0:
        logger.info(
            "  [OK] Commission %.4f %s for orderId=%s, context exists, would update DB",
            commission, currency, oid,
        )

    # Also check for the 1e10 sentinel (IBKR reports this when commission is unknown)
    if commission >= 1e9:
        logger.warning(
            "  [IBKR] Sentinel commission value %.2f detected — IBKR reports this when "
            "commission is not yet known. A second commissionReport with real value may follow.",
            commission,
        )


def on_error(reqId, errorCode, errorString, contract):
    sym = getattr(contract, "symbol", "") if contract else ""
    logger.warning("[ERROR] reqId=%s code=%s msg=%s contract=%s", reqId, errorCode, errorString, sym)


async def test_listen_only(ib, account):
    """Mode 1: just listen for commission events on existing fills."""
    logger.info("=" * 70)
    logger.info("MODE: Listen-only (no orders placed)")
    logger.info("Requesting executions and waiting for commissionReport events...")
    logger.info("=" * 70)

    fills = ib.fills()
    logger.info("Current fills in IB session: %d", len(fills))
    for f in fills:
        logger.info(
            "  Fill: orderId=%s execId=%s symbol=%s side=%s qty=%s price=%s commission=%s",
            f.contract.conId, f.execution.execId, f.contract.symbol,
            f.execution.side, f.execution.shares, f.execution.price,
            f.commissionReport.commission if f.commissionReport else "N/A",
        )
        if f.commissionReport:
            cr = f.commissionReport
            logger.info(
                "    CommissionReport: commission=%.4f currency=%s realizedPNL=%.2f",
                float(cr.commission or 0), cr.currency or "", float(cr.realizedPNL or 0),
            )

    # Request today's executions explicitly
    logger.info("\nRequesting reqExecutions (today's fills)...")
    exec_fills = await ib.reqExecutionsAsync()
    logger.info("reqExecutions returned %d fills", len(exec_fills))
    for f in exec_fills:
        logger.info(
            "  Execution: execId=%s symbol=%s side=%s qty=%s price=%s time=%s",
            f.execution.execId, f.contract.symbol,
            f.execution.side, f.execution.shares, f.execution.price,
            f.execution.time,
        )
        if f.commissionReport:
            cr = f.commissionReport
            logger.info(
                "    CommissionReport: commission=%.4f currency=%s realizedPNL=%.2f",
                float(cr.commission or 0), cr.currency or "", float(cr.realizedPNL or 0),
            )
        else:
            logger.warning("    CommissionReport: NONE (not yet available)")

    logger.info("\nWaiting 10s for any delayed commissionReport events...")
    await asyncio.sleep(10)


async def test_with_order(ib, account):
    """Mode 2: place a small order and track the full event sequence."""
    import ib_insync

    logger.info("=" * 70)
    logger.info("MODE: Place order (1 share of SPY)")
    logger.info("=" * 70)

    contract = ib_insync.Stock("SPY", "SMART", "USD")
    qualified = await ib.qualifyContractsAsync(contract)
    if not qualified:
        logger.error("Failed to qualify SPY contract!")
        return

    order_id_before = ib.client.getReqId()
    logger.info("Next orderId will be around: %s", order_id_before)

    # Register context BEFORE placing order (simulating IBKRClient behavior)
    simulated_contexts[order_id_before] = {"symbol": "SPY", "strategy_id": 999}

    order = ib_insync.MarketOrder("BUY", 1, account=account, tif="IOC")
    trade = ib.placeOrder(contract, order)
    actual_oid = trade.order.orderId

    if actual_oid != order_id_before:
        simulated_contexts[actual_oid] = simulated_contexts.pop(order_id_before, {})

    logger.info("Order placed: orderId=%s", actual_oid)
    timeline.record("order_placed", actual_oid, {"symbol": "SPY", "qty": 1, "tif": "IOC"})

    logger.info("Waiting 30s for all events to complete...")
    await asyncio.sleep(30)

    # Check final state
    logger.info("\n--- Post-order check ---")
    for t in ib.trades():
        if t.order.orderId == actual_oid:
            logger.info(
                "Trade status: orderId=%s status=%s filled=%s avgPrice=%s",
                t.order.orderId, t.orderStatus.status,
                t.orderStatus.filled, t.orderStatus.avgFillPrice,
            )
            for log_entry in (t.log or []):
                logger.info("  Log: %s %s", log_entry.time, log_entry.message)


async def main():
    place_order = "--place-order" in sys.argv

    try:
        import ib_insync
    except ImportError:
        logger.error("ib_insync not installed. Run: pip install ib_insync")
        return

    ib = ib_insync.IB()
    ib.RequestTimeout = 30

    ib.orderStatusEvent += on_order_status
    ib.execDetailsEvent += on_exec_details
    ib.commissionReportEvent += on_commission_report
    ib.errorEvent += on_error

    logger.info("Connecting to IBKR at %s:%s...", IBKR_HOST, IBKR_PORT)
    try:
        await ib.connectAsync(host=IBKR_HOST, port=IBKR_PORT, clientId=998, readonly=not place_order, timeout=20)
    except Exception as e:
        logger.error("Connection failed: %s", e)
        return

    accounts = ib.managedAccounts()
    account = IBKR_ACCOUNT or (accounts[0] if accounts else None)
    logger.info("Connected! Account: %s", account)

    try:
        if place_order:
            await test_with_order(ib, account)
        else:
            await test_listen_only(ib, account)
    finally:
        timeline.print_summary()
        ib.disconnect()
        logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
