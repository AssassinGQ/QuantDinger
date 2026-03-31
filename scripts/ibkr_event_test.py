#!/usr/bin/env python3
"""IBKR Event Test Script - 验证 reqPnLSingle 触发哪些回调"""
import asyncio
import ib_insync
import logging
import sys
import os
from datetime import datetime

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/ibkr_test/event_log.txt', mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('ibkr_event_test')

IBKR_HOST = os.environ.get('IBKR_HOST', 'ib-gateway')
IBKR_PORT = int(os.environ.get('IBKR_PORT', '4004'))
IBKR_ACCOUNT = os.environ.get('IBKR_ACCOUNT', '')

CALLED_EVENTS = []

def log_event(name, **kwargs):
    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    CALLED_EVENTS.append(name)
    logger.info(f"[EVENT @ {timestamp}] {name}: {kwargs}")

def on_error(reqId, errorCode, errorString, advancedOrderRejectJson=''):
    log_event('errorEvent', reqId=reqId, code=errorCode, msg=errorString)

def on_connected():
    logger.info("=== IB Connected ===")

def on_disconnected():
    logger.info("=== IB Disconnected ===")

def on_update():
    log_event('updateEvent')

def on_pnl(pnl):
    """ib_insync 传的是单个 PnL 对象"""
    log_event('pnlEvent', account=pnl.account, dailyPnL=pnl.dailyPnL, 
              unrealizedPnL=pnl.unrealizedPnL, realizedPnL=pnl.realizedPnL)

def on_pnl_single(pnlSingle):
    """ib_insync 传的是单个 PnLSingle 对象"""
    log_event('pnlSingleEvent', account=pnlSingle.account, modelCode=pnlSingle.modelCode,
              conId=pnlSingle.conId, dailyPnL=pnlSingle.dailyPnL, 
              unrealizedPnL=pnlSingle.unrealizedPnL, realizedPnL=pnlSingle.realizedPnL,
              position=pnlSingle.position, value=pnlSingle.value)

def on_update_portfolio(item):
    log_event('updatePortfolioEvent', symbol=item.contract.symbol, conId=item.contract.conId,
              unrealPNL=item.unrealizedPNL, realizedPNL=item.realizedPNL, mktValue=item.marketValue)

def on_position(position):
    log_event('positionEvent', symbol=position.contract.symbol, conId=position.contract.conId,
              account=position.account, pos=position.position, avgCost=position.avgCost)

def on_account_value(value):
    log_event('accountValueEvent', tag=value.tag, value=value.value, currency=value.currency)

def on_pending_tickers(tickers):
    log_event('pendingTickersEvent')

def on_timeout(idlePeriod):
    log_event('timeoutEvent', idlePeriod=idlePeriod)

async def main():
    ib = ib_insync.IB()
    ib.RequestTimeout = 30

    ib.errorEvent += on_error
    ib.connectedEvent += on_connected
    ib.disconnectedEvent += on_disconnected
    ib.updateEvent += on_update
    ib.pnlEvent += on_pnl
    ib.pnlSingleEvent += on_pnl_single
    ib.updatePortfolioEvent += on_update_portfolio
    ib.positionEvent += on_position
    ib.accountValueEvent += on_account_value
    ib.pendingTickersEvent += on_pending_tickers
    ib.timeoutEvent += on_timeout

    logger.info(f"Connecting to IBKR Gateway at {IBKR_HOST}:{IBKR_PORT}...")
    try:
        await ib.connectAsync(host=IBKR_HOST, port=IBKR_PORT, clientId=999, readonly=True, timeout=20)
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        return

    accounts = ib.managedAccounts()
    ACCOUNT = IBKR_ACCOUNT if IBKR_ACCOUNT else (accounts[0] if accounts else None)
    logger.info(f"Connected! Account: {ACCOUNT}")

    logger.info("=" * 60)
    logger.info("STEP 1: reqPositionsAsync")
    logger.info("=" * 60)
    positions = await ib.reqPositionsAsync()
    logger.info(f"Found {len(positions)} positions")
    for pos in positions:
        logger.info(f"  - {pos.contract.symbol} (conId={pos.contract.conId}): {pos.position} @ avgCost={pos.avgCost}")

    if not positions:
        logger.warning("No positions found!")
        ib.disconnect()
        return

    logger.info("=" * 60)
    logger.info("STEP 2: Activate reqPnL")
    logger.info("=" * 60)
    ib.reqPnL(ACCOUNT)
    logger.info("reqPnL called, waiting 5s...")
    await asyncio.sleep(5)

    logger.info("=" * 60)
    logger.info("STEP 3: Call reqPnLSingle for each position")
    logger.info("=" * 60)
    for pos in positions:
        logger.info(f"Calling reqPnLSingle for {pos.contract.symbol} (conId={pos.contract.conId})")
        try:
            ib.reqPnLSingle(ACCOUNT, "", pos.contract.conId)
            logger.info(f"  -> reqPnLSingle returned OK")
        except Exception as e:
            logger.error(f"  -> reqPnLSingle failed: {e}")

    logger.info("=" * 60)
    logger.info("STEP 4: Wait 15 seconds for callbacks")
    logger.info("=" * 60)
    await asyncio.sleep(15)

    logger.info("=" * 60)
    logger.info("SUMMARY: Events triggered")
    logger.info("=" * 60)
    unique_events = sorted(set(CALLED_EVENTS))
    for e in unique_events:
        count = CALLED_EVENTS.count(e)
        logger.info(f"  {e}: {count} times")
    
    logger.info("=" * 60)
    logger.info("DETAILED pnlSingleEvent calls:")
    logger.info("=" * 60)
    
    ib.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
