#!/usr/bin/env python3
"""IBKR 持仓、挂单和账户查询 (只读)"""

import argparse
from ib_insync import IB

DEFAULT_HOST = 'ib-gateway'
DEFAULT_PORT = 4004
DEFAULT_CLIENT_ID = 99


def query_positions(ib):
    positions = ib.positions()
    if not positions:
        print("当前无持仓")
        return

    print("=== 持仓 ===")
    for p in positions:
        contract = p.contract
        symbol = contract.symbol
        sec_type = contract.secType
        position = p.position
        avg_cost = p.avgCost

        try:
            ticker = ib.reqMktData(contract, '', False, False)
            ib.sleep(0.5)
            market_value = ticker.bid if ticker.bid else ticker.close
            if market_value:
                unrealized = (market_value - avg_cost) * position
                print(f"{symbol} {sec_type} Qty:{position} AvgCost:{avg_cost:.2f} MktValue:{market_value:.2f} Unrealized:{unrealized:+.2f}")
                continue
        except Exception:
            pass

        print(f"{symbol} {sec_type} Qty:{position} AvgCost:{avg_cost:.2f}")


def query_open_orders(ib):
    trades = ib.openTrades()
    if not trades:
        print("当前无挂单")
        return

    by_status = {}
    for t in trades:
        s = t.orderStatus.status
        by_status.setdefault(s, []).append(t)

    print(f"=== 挂单 ({len(trades)} 条) ===")
    for status, group in sorted(by_status.items()):
        print(f"\n--- {status} ({len(group)} 条) ---")
        for t in group:
            o = t.order
            c = t.contract
            filled = t.orderStatus.filled or 0
            remaining = t.orderStatus.remaining or 0
            print(
                f"  orderId={o.orderId} {o.action} {o.totalQuantity} "
                f"{c.symbol} ({c.secType}) type={o.orderType} "
                f"filled={filled} remaining={remaining}"
            )


def query_account(ib):
    print("\n=== 账户概况 ===")
    acct = ib.accountSummary()

    key_tags = [
        'NetLiquidation', 'TotalCashValue', 'StockMarketValue',
        'AvailableFunds', 'BuyingPower', 'UnrealizedPnL',
        'RealizedPnL', 'GrossPositionValue', 'InitMarginReq',
        'MaintMarginReq', 'AccruedCash',
    ]

    acct_dict = {a.tag: (a.value, a.currency) for a in acct}

    for tag in key_tags:
        if tag in acct_dict:
            value, currency = acct_dict[tag]
            try:
                num_val = float(value)
                if abs(num_val) >= 1000000:
                    formatted = f"{num_val/1000000:.2f}M"
                elif abs(num_val) >= 1000:
                    formatted = f"{num_val/1000:.2f}K"
                else:
                    formatted = f"{num_val:.2f}"
                print(f"{tag}: {currency} {formatted} ({value})")
            except Exception:
                print(f"{tag}: {value} ({currency})")


def main():
    parser = argparse.ArgumentParser(description='IBKR 持仓、挂单和账户查询 (只读)')
    parser.add_argument('--host', default=DEFAULT_HOST)
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    parser.add_argument('--client-id', type=int, default=DEFAULT_CLIENT_ID)
    parser.add_argument('--positions-only', action='store_true')
    parser.add_argument('--orders-only', action='store_true')
    parser.add_argument('--account-only', action='store_true')
    args = parser.parse_args()

    ib = IB()
    try:
        print(f"连接 IB Gateway ({args.host}:{args.port}, clientId={args.client_id})...")
        ib.connect(args.host, args.port, clientId=args.client_id)
        print("连接成功\n")

        if args.positions_only:
            query_positions(ib)
        elif args.orders_only:
            query_open_orders(ib)
        elif args.account_only:
            query_account(ib)
        else:
            query_positions(ib)
            print()
            query_open_orders(ib)
            query_account(ib)

    except Exception as e:
        print(f"连接失败: {e}")
        return 1
    finally:
        ib.disconnect()

    return 0


if __name__ == '__main__':
    exit(main())
