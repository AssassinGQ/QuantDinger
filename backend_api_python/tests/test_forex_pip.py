"""forex_pip.pip_size_for_forex_symbol (phase 17 TRADE-03)."""

from app.services.live_trading.forex_pip import pip_size_for_forex_symbol


def test_uc_03a_pip_jpy_pair():
    assert pip_size_for_forex_symbol("USDJPY") == 0.01


def test_uc_03b_pip_non_jpy():
    assert pip_size_for_forex_symbol("EURUSD") == 0.0001
