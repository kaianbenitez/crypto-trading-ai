"""Smoke script for the scanner's mainnet-liquidity sourcing, abnormal-move
filter, and single-letter-base filter (agent/adapt/roster.py).
Run directly: `python3 tests/smoke_market_scan_mainnet_liquidity.py`.

Verifies:
- when MARKET_SCAN_USE_MAINNET_LIQUIDITY + Binance + testnet, ranking uses
  the mocked mainnet ticker data instead of the adapter's (inflated) testnet
  data — a symbol with big testnet-only volume but thin real volume is
  correctly rejected, and vice versa
- liquidity_source is reported correctly ("mainnet_public" vs "adapter")
- graceful fallback to adapter tickers (with liquidity_source="adapter")
  when the mainnet fetch fails
- a symbol tradable on testnet but absent from mainnet data is rejected as
  bad_data (never silently trusted on testnet-only numbers)
- no-op on live/mainnet trading (binance_testnet=False) or non-Binance
- abnormal 24h moves are rejected before ranking (regardless of liquidity)
- single-letter-base filter is off by default, works when enabled
- selected_detail carries per-candidate quote_volume/pct_change/spread_pct/score
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.config.settings import settings  # noqa: E402
from agent.adapt import roster as roster_mod  # noqa: E402
from agent.adapt.roster import discover_market_universe  # noqa: E402

failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        failures.append(label)


def _ticker(quote_volume, last=1.0, pct=0.0, bid=None, ask=None):
    t = {"quoteVolume": quote_volume, "last": last, "percentage": pct}
    if bid is not None:
        t["bid"] = bid
    if ask is not None:
        t["ask"] = ask
    return t


class FakeAdapter:
    def __init__(self, tickers):
        self._tickers = tickers

    def fetch_all_tickers(self):
        return self._tickers


def _base_settings():
    settings.market_scan_min_quote_volume = 50_000_000
    settings.market_scan_max_spread_pct = 0.5
    settings.market_scan_top_n = 10
    settings.market_scan_include_fixed_majors = False
    settings.market_scan_fixed_majors = ""
    settings.market_scan_exclude_symbols = ""
    settings.market_scan_require_market_cap_rank = False
    settings.market_scan_max_abs_24h_change_pct = 35
    settings.market_scan_exclude_single_letter_bases = False
    settings.exchange = "binance"
    settings.binance_testnet = True
    settings.market_scan_use_mainnet_liquidity = True


def test_mainnet_liquidity_used_over_testnet_volume():
    """The headline scenario: a symbol with huge TESTNET volume but thin
    real (mainnet) volume must be rejected; a symbol that looks thin on
    testnet but is genuinely liquid on mainnet must be selected."""
    _base_settings()

    # Testnet (adapter) tickers: PUMPED has fake huge testnet volume; REAL
    # looks unremarkable on testnet.
    testnet_tickers = {
        "PUMPED/USDT:USDT": _ticker(900_000_000, last=1.0, pct=2.0, bid=1.0, ask=1.001),
        "REAL/USDT:USDT": _ticker(60_000_000, last=100.0, pct=1.5, bid=100.0, ask=100.05),
    }
    # Mainnet reality: PUMPED is actually illiquid; REAL is genuinely liquid.
    mainnet_tickers = {
        "PUMPED/USDT:USDT": _ticker(5_000_000, last=1.0, pct=2.0, bid=1.0, ask=1.05),
        "REAL/USDT:USDT": _ticker(400_000_000, last=100.0, pct=1.5, bid=100.0, ask=100.05),
    }
    original_fetch = roster_mod.fetch_mainnet_liquidity_tickers
    roster_mod.fetch_mainnet_liquidity_tickers = lambda: mainnet_tickers
    try:
        adapter = FakeAdapter(testnet_tickers)
        selected, meta = discover_market_universe(adapter)
        check("liquidity_source reported as mainnet_public", meta["liquidity_source"] == "mainnet_public")
        check("PUMPED rejected — real (mainnet) volume is thin despite huge testnet volume", "PUMPED/USDT" not in selected)
        check("REAL selected — genuinely liquid on mainnet despite unremarkable testnet ticker", "REAL/USDT" in selected)
        check("PUMPED counted under low_volume, not silently passed", meta["rejected"]["low_volume"] >= 1)
    finally:
        roster_mod.fetch_mainnet_liquidity_tickers = original_fetch


def test_fallback_when_mainnet_fetch_fails():
    _base_settings()
    tickers = {"BTC/USDT:USDT": _ticker(200_000_000, last=60000, pct=1.0, bid=60000, ask=60010)}
    original_fetch = roster_mod.fetch_mainnet_liquidity_tickers
    roster_mod.fetch_mainnet_liquidity_tickers = lambda: None  # simulated failure
    try:
        adapter = FakeAdapter(tickers)
        selected, meta = discover_market_universe(adapter)
        check("Falls back to liquidity_source='adapter' when mainnet fetch fails", meta["liquidity_source"] == "adapter")
        check("Still selects using adapter data as the fallback source", "BTC/USDT" in selected)
    finally:
        roster_mod.fetch_mainnet_liquidity_tickers = original_fetch


def test_testnet_only_symbol_rejected_as_bad_data():
    """A symbol tradable on testnet but with no mainnet counterpart at all
    must never be silently judged 'liquid' off testnet-only numbers."""
    _base_settings()
    tickers = {"TESTNETONLY/USDT:USDT": _ticker(900_000_000, last=1.0, pct=1.0)}
    original_fetch = roster_mod.fetch_mainnet_liquidity_tickers
    # Mainnet fetch SUCCEEDS (non-empty, so it's used) but simply has no
    # listing for this symbol at all — distinct from a fetch failure.
    roster_mod.fetch_mainnet_liquidity_tickers = lambda: {"BTC/USDT:USDT": _ticker(500_000_000, last=60000, pct=1.0)}
    try:
        adapter = FakeAdapter(tickers)
        selected, meta = discover_market_universe(adapter)
        check("Symbol absent from mainnet data is rejected, not trusted on testnet numbers", "TESTNETONLY/USDT" not in selected)
        check("Rejected as bad_data", meta["rejected"]["bad_data"] >= 1)
    finally:
        roster_mod.fetch_mainnet_liquidity_tickers = original_fetch


def test_noop_on_live_trading_and_non_binance():
    _base_settings()
    tickers = {"BTC/USDT:USDT": _ticker(200_000_000, last=60000, pct=1.0, bid=60000, ask=60010)}

    called = {"n": 0}
    original_fetch = roster_mod.fetch_mainnet_liquidity_tickers

    def _tracking_fetch():
        called["n"] += 1
        return {}

    roster_mod.fetch_mainnet_liquidity_tickers = _tracking_fetch
    try:
        settings.binance_testnet = False  # live trading -> no-op
        _, meta = discover_market_universe(FakeAdapter(tickers))
        check("No mainnet fetch attempted when already trading live", called["n"] == 0)
        check("liquidity_source is 'adapter' on live trading", meta["liquidity_source"] == "adapter")

        settings.binance_testnet = True
        settings.exchange = "bybit"  # non-Binance -> no-op
        _, meta2 = discover_market_universe(FakeAdapter(tickers))
        check("No mainnet fetch attempted for a non-Binance exchange", called["n"] == 0)
        check("liquidity_source is 'adapter' for non-Binance exchange", meta2["liquidity_source"] == "adapter")
    finally:
        roster_mod.fetch_mainnet_liquidity_tickers = original_fetch
        settings.exchange = "binance"
        settings.binance_testnet = True


def test_abnormal_move_rejected():
    _base_settings()
    tickers = {
        "NORMAL/USDT:USDT": _ticker(200_000_000, last=100.0, pct=8.0, bid=100.0, ask=100.05),
        "CRASH/USDT:USDT": _ticker(200_000_000, last=1.0, pct=-51.0, bid=1.0, ask=1.001),
        "PUMP/USDT:USDT": _ticker(200_000_000, last=1.0, pct=68.0, bid=1.0, ask=1.001),
    }
    settings.market_scan_use_mainnet_liquidity = False  # isolate this filter from liquidity sourcing
    adapter = FakeAdapter(tickers)
    selected, meta = discover_market_universe(adapter)
    check("Normal 8% move is selected", "NORMAL/USDT" in selected)
    check("-51% crash mover is rejected", "CRASH/USDT" not in selected)
    check("+68% pump mover is rejected", "PUMP/USDT" not in selected)
    check("abnormal_move rejection count == 2", meta["rejected"]["abnormal_move"] == 2)


def test_single_letter_base_filter():
    _base_settings()
    settings.market_scan_use_mainnet_liquidity = False
    tickers = {
        "M/USDT:USDT": _ticker(200_000_000, last=1.0, pct=1.0, bid=1.0, ask=1.001),
        "BTC/USDT:USDT": _ticker(200_000_000, last=60000, pct=1.0, bid=60000, ask=60010),
    }
    adapter = FakeAdapter(tickers)

    selected_off, meta_off = discover_market_universe(adapter)
    check("Single-letter base passes when filter is off (default)", "M/USDT" in selected_off)
    check("single_letter_base count is 0 when disabled", meta_off["rejected"]["single_letter_base"] == 0)

    settings.market_scan_exclude_single_letter_bases = True
    selected_on, meta_on = discover_market_universe(adapter)
    check("Single-letter base rejected when filter is enabled", "M/USDT" not in selected_on)
    check("BTC unaffected by the single-letter filter", "BTC/USDT" in selected_on)
    check("single_letter_base rejection recorded", meta_on["rejected"]["single_letter_base"] == 1)
    settings.market_scan_exclude_single_letter_bases = False


def test_selected_detail_metadata():
    _base_settings()
    settings.market_scan_use_mainnet_liquidity = False
    tickers = {
        "BTC/USDT:USDT": _ticker(500_000_000, last=60000, pct=2.0, bid=60000, ask=60010),
        "ETH/USDT:USDT": _ticker(300_000_000, last=3000, pct=1.0, bid=3000, ask=3001),
    }
    selected, meta = discover_market_universe(FakeAdapter(tickers))
    check("selected_detail present with an entry per selected symbol", len(meta["selected_detail"]) == len(selected))
    detail = meta["selected_detail"][0]
    for key in ("symbol", "quote_volume", "pct_change", "spread_pct", "score"):
        check(f"selected_detail entries carry '{key}'", key in detail)


def main():
    test_mainnet_liquidity_used_over_testnet_volume()
    test_fallback_when_mainnet_fetch_fails()
    test_testnet_only_symbol_rejected_as_bad_data()
    test_noop_on_live_trading_and_non_binance()
    test_abnormal_move_rejected()
    test_single_letter_base_filter()
    test_selected_detail_metadata()

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
