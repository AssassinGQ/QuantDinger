#!/usr/bin/env python3
"""
Cancel all PreSubmitted orders on IB Gateway.

Usage (from SSH container, inside Docker network):
    python cancel_all_presubmit.py --host ib-gateway --port 4004

Usage (from NAS host, via mapped port):
    python cancel_all_presubmit.py --host 127.0.0.1 --port 4002
"""

import argparse
import time
import sys


def main():
    parser = argparse.ArgumentParser(description="Cancel all PreSubmitted orders on IB Gateway")
    parser.add_argument("--host", default="ib-gateway", help="IB Gateway host")
    parser.add_argument("--port", type=int, default=4004, help="IB Gateway port (paper: 4004)")
    parser.add_argument("--client-id", type=int, default=99, help="Client ID (use different from live strategy)")
    parser.add_argument("--dry-run", action="store_true", help="Only list, don't cancel")
    args = parser.parse_args()

    try:
        from ib_insync import IB
    except ImportError:
        print("ERROR: ib_insync not installed. Run: pip install ib_insync")
        sys.exit(1)

    ib = IB()
    print(f"Connecting to {args.host}:{args.port} (clientId={args.client_id})...")
    try:
        ib.connect(args.host, args.port, clientId=args.client_id, timeout=15)
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    print(f"Connected. Account: {ib.managedAccounts()}")

    trades = ib.openTrades()
    print(f"\nTotal open trades: {len(trades)}")

    presubmitted = [t for t in trades if t.orderStatus.status == "PreSubmitted"]
    submitted = [t for t in trades if t.orderStatus.status == "Submitted"]
    other = [t for t in trades if t.orderStatus.status not in ("PreSubmitted", "Submitted")]

    print(f"  PreSubmitted: {len(presubmitted)}")
    print(f"  Submitted:    {len(submitted)}")
    print(f"  Other:        {len(other)}")

    if not presubmitted:
        print("\nNo PreSubmitted orders to cancel.")
        ib.disconnect()
        return

    print(f"\n{'='*60}")
    print(f"PreSubmitted orders to cancel:")
    print(f"{'='*60}")
    for i, t in enumerate(presubmitted):
        print(
            f"  [{i+1}] orderId={t.order.orderId} "
            f"{t.order.action} {t.order.totalQuantity} "
            f"{t.contract.symbol} ({t.contract.secType}) "
            f"type={t.order.orderType}"
        )

    if args.dry_run:
        print(f"\n[DRY RUN] Would cancel {len(presubmitted)} orders.")
        ib.disconnect()
        return

    print(f"\nCancelling {len(presubmitted)} PreSubmitted orders...")
    cancelled = 0
    for t in presubmitted:
        try:
            ib.cancelOrder(t.order)
            cancelled += 1
        except Exception as e:
            print(f"  Failed to cancel orderId={t.order.orderId}: {e}")

    ib.sleep(2)
    print(f"\nCancelled {cancelled}/{len(presubmitted)} orders.")

    remaining = ib.openTrades()
    remaining_pre = [t for t in remaining if t.orderStatus.status == "PreSubmitted"]
    print(f"Remaining open trades: {len(remaining)} (PreSubmitted: {len(remaining_pre)})")

    ib.disconnect()
    print("Done.")


if __name__ == "__main__":
    main()
