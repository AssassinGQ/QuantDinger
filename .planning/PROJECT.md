# PROJECT

## Project Overview

QuantDinger3 is a quantitative trading platform with multi-market strategy execution, including IBKR live/paper trading paths.

## Milestone History

### Milestone M1: IBKR data-sufficiency risk gate for open signals

**Status:** in progress (Phase 1 domain model delivered 2026-04-17)  
**Created:** 2026-04-16

#### Goal

For IBKR strategies (both `ibkr-paper` and `ibkr-live`), add a unified mechanism that:

1. Computes whether market data is sufficient for the strategy's required lookback/data volume.
2. Uses IBKR trading-day/session information to evaluate data freshness/completeness.
3. Blocks new open-position signals when data is insufficient.
4. Sends user alerts through strategy-configured notification channels.
5. Lets users decide whether to close existing positions (warn + decision support, not forced auto-close).

#### Why this milestone

- Missing trading-day bars can silently invalidate strategy context.
- Opening new positions with stale/incomplete data creates avoidable risk.
- Existing alerts need to become strategy-aware and decision-oriented for IBKR execution modes.

#### Success Criteria

- IBKR strategies do not open positions when data sufficiency checks fail.
- Alert payload clearly explains insufficiency reason, missing window, and current position state.
- Behavior is consistent between `ibkr-paper` and `ibkr-live`.
- Test coverage includes positive/negative sufficiency paths and open-block behavior.
