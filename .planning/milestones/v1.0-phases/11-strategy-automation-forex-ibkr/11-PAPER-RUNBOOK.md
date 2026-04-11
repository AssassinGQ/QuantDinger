# Phase 11 — IBKR Paper EURUSD operator runbook

Manual checklist for validating Forex automation against **IBKR Paper** (IDEALPRO) with **EURUSD**, alongside the automated test gates in this phase.

## Prerequisites

- **IBKR TWS or IB Gateway** running in **Paper** trading mode (not live).
- **API socket enabled** in TWS/Gateway: **Configure → API → Settings** — enable ActiveX and Socket Clients; note the port (default **7497** for paper; live is often 7496).
- **QuantDinger backend** running per project norm: from repo root `docker-compose up`, or run `backend_api_python` locally with the same database and env as your environment.
- Strategy credentials: if the strategy stores `ibkr_host` / `ibkr_port` in `exchange_config`, they must point at the machine where TWS/Gateway listens (often `127.0.0.1` and **7497** for paper).

## Strategy configuration (EURUSD)

Set these explicitly when creating or editing the strategy (API or UI):

- `market_category` = **Forex**
- `exchange_config.exchange_id` = **ibkr-paper** (use **ibkr-live** only when you intend live; this runbook assumes paper)
- `trading_config.symbol` = **EURUSD**
- `trading_config.market_type` = **forex** (this is the value persisted to `qd_strategies_trading.market_type` and passed through `load_strategy_configs`; the worker lowercases it to `forex` for routing)
- `execution_mode` = **live** when you want orders to flow through the pending worker to IBKR (otherwise the worker stays in signal-only mode)

## Operator steps (paper EURUSD)

1. Start **TWS or Gateway** in **Paper** mode and confirm the API port (**7497** default for paper).
2. Start the **QuantDinger backend** (e.g. `docker-compose up` from the repo root).
3. **Create or select** a strategy with the keys above; ensure the strategy is **enabled/started** per your deployment (status and scheduler as required by your setup).
4. **Connect** the IBKR client path used by the worker (first live order may establish the connector; watch backend logs for connection errors).
5. **Trigger or wait for** an opening signal (e.g. `open_long` / `open_short` for EURUSD) so a **live** pending order is enqueued and processed.
6. **Confirm** submission or fill: backend logs, `pending_orders` / trade tables, or TWS **Executions** for EURUSD on **IDEALPRO**.
7. **Trigger or wait for** a closing signal (`close_long` / `close_short`) to flatten.
8. **Reconcile**: position size for EURUSD near **zero**, and PnL / fills rows consistent with open and close (per your DB and log conventions).

## Verify (automated) — full backend suite

Run from the repository root (or `backend_api_python` as the working directory):

```bash
cd backend_api_python && python -m pytest tests/ -q
```

## Phase 11 test subset (IBKR Forex automation)

```bash
cd backend_api_python && python -m pytest tests/test_strategy_exchange_validation.py tests/test_forex_ibkr_e2e.py tests/test_ibkr_forex_paper_smoke.py -q
```

This subset covers save-time exchange validation, Flask + worker E2E mocks, and mock IBKR Paper smoke callbacks for multiple pairs.
