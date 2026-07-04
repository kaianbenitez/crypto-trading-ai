"""Smoke script for agent/dashboard/trade_narrative.py — no pytest dependency,
run directly: `python3 tests/smoke_trade_narrative.py` (or via the venv on the
VPS: `venv/bin/python -m tests.smoke_trade_narrative` from the repo root).

Verifies the fact-based composer actually varies with the underlying data
instead of producing templated, near-identical text across trades.
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.db.models import Trade, get_session  # noqa: E402
from agent.dashboard.trade_narrative import build_narrative  # noqa: E402

failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        failures.append(label)


def make_trade(session, **overrides) -> Trade:
    defaults = dict(
        symbol="BTC/USDT",
        side="long",
        strategy_name="trend_following",
        regime="trending",
        entry_price=100.0,
        qty=1.0,
        stop_loss=98.0,
        take_profit=104.0,
        leverage=3,
    )
    defaults.update(overrides)
    snapshot = defaults.pop("snapshot", {})
    reasoning = defaults.pop("reasoning", ["Regime: trending (ADX=40.0)"])
    outcome = defaults.pop("outcome", None)
    exit_reason = defaults.pop("exit_reason", None)
    pnl_usdt = defaults.pop("pnl_usdt", None)
    closed_at = defaults.pop("closed_at", None)
    opened_at = defaults.pop("opened_at", datetime.utcnow() - timedelta(hours=1))

    trade = Trade(**defaults, opened_at=opened_at)
    trade.set_entry_reasoning(reasoning)
    trade.set_indicator_snapshot(snapshot)
    trade.set_params_snapshot({})
    trade.outcome = outcome
    trade.exit_reason = exit_reason
    trade.pnl_usdt = pnl_usdt
    trade.closed_at = closed_at
    session.add(trade)
    session.commit()
    return trade


def main():
    session = get_session("sqlite:///:memory:")

    # --- 1. BTC premium-zone long vs BNB pullback long should read differently ---
    btc = make_trade(
        session,
        symbol="BTC/USDT",
        reasoning=["Regime: trending (ADX=40.0)", "Price in PREMIUM zone (0.85) — unfavourable for longs"],
        snapshot={"range_position": 0.85, "mtf_bias": "bullish", "mtf_ev": 1.66, "min_required_ev_r": 0.42,
                  "confidence": 0.5, "mtf_score": 70},
    )
    bnb = make_trade(
        session,
        symbol="BNB/USDT",
        reasoning=["Regime: trending (ADX=35.0)"],
        snapshot={"range_position": 0.2, "mtf_bias": "bullish", "mtf_ev": 0.9, "min_required_ev_r": 0.3,
                  "confidence": 0.6, "mtf_score": 65},
    )
    n_btc = build_narrative(btc, session)
    n_bnb = build_narrative(bnb, session)
    check("BTC (premium-zone) and BNB (pullback) thesis text differs", n_btc.thesis_lines != n_bnb.thesis_lines)
    check("BTC premium-zone weakness flagged", n_btc.weakness_line is not None and "premium" in n_btc.weakness_line.lower())
    check("BNB pullback has no premium-zone weakness", n_bnb.weakness_line is None or "premium" not in (n_bnb.weakness_line or "").lower())
    check("BTC thesis mentions late/upper-range entry", "late" in n_btc.thesis_lines[-1].lower() or "upper" in n_btc.thesis_lines[-1].lower())
    check("BNB thesis mentions pullback-like entry", "pullback" in n_bnb.thesis_lines[-1].lower() or "lower" in n_bnb.thesis_lines[-1].lower())

    # --- 2. Long discount-zone vs short discount-zone should differ in framing ---
    short_discount = make_trade(
        session,
        symbol="AVAX/USDT",
        side="short",
        reasoning=["Regime: trending (ADX=30.0)"],
        snapshot={"range_position": 0.15, "mtf_bias": "bearish", "mtf_ev": 1.0, "min_required_ev_r": 0.3},
    )
    n_short = build_narrative(short_discount, session)
    check("Short at range low warns about discount-zone chase", "discount" in n_short.thesis_lines[-1].lower())

    # --- 3. No same-symbol history vs a stopped-out last trade differ ---
    fresh_symbol = make_trade(session, symbol="FIL/USDT", snapshot={})
    n_fresh = build_narrative(fresh_symbol, session)
    check("No-history past context says 'no useful sample'", "no useful" in n_fresh.past_context_line.lower())

    link1 = make_trade(
        session, symbol="LINK/USDT",
        outcome="loss", exit_reason="stop_loss", pnl_usdt=-5.0,
        closed_at=datetime.utcnow() - timedelta(hours=2),
        opened_at=datetime.utcnow() - timedelta(hours=3),
    )
    link2 = make_trade(session, symbol="LINK/USDT", snapshot={})
    n_link = build_narrative(link2, session)
    check("Past-loss context mentions stopped out", "stopped out" in n_link.past_context_line.lower())
    check("Fresh-symbol and past-loss contexts differ", n_fresh.past_context_line != n_link.past_context_line)

    # --- 4. Thin EV vs comfortable EV should produce different why-accepted wording ---
    thin_ev = make_trade(
        session, symbol="DOT/USDT",
        snapshot={"mtf_ev": 0.32, "min_required_ev_r": 0.30, "confidence": 0.4, "mtf_score": 55},
    )
    strong_ev = make_trade(
        session, symbol="UNI/USDT",
        snapshot={"mtf_ev": 2.0, "min_required_ev_r": 0.3, "confidence": 0.7, "mtf_score": 80},
    )
    n_thin = build_narrative(thin_ev, session)
    n_strong = build_narrative(strong_ev, session)
    check("Thin-EV why-accepted text differs from strong-EV", n_thin.why_accepted_lines != n_strong.why_accepted_lines)
    check("Thin-EV wording flags thin edge", any("thin" in line.lower() for line in n_thin.why_accepted_lines))
    check("Strong-EV wording flags comfortable clearance", any("comfortably" in line.lower() for line in n_strong.why_accepted_lines))

    # --- 5. Risk reduction should be explained when actual < planned ---
    reduced_risk = make_trade(
        session, symbol="ATOM/USDT",
        snapshot={"actual_risk_pct": 0.45, "planned_risk_pct": 1.5, "risk_tier": "normal"},
    )
    n_reduced = build_narrative(reduced_risk, session)
    check("Risk reduction explained in why-accepted", any("reduced" in line.lower() for line in n_reduced.why_accepted_lines))

    # --- 6. Closed loss with a weakness ties the failure line back to it ---
    closed_loss = make_trade(
        session, symbol="SOL/USDT",
        reasoning=["Regime: trending (ADX=25.0)", "Price in PREMIUM zone (0.9) — unfavourable for longs"],
        snapshot={"range_position": 0.9},
        outcome="loss", exit_reason="stop_loss", pnl_usdt=-8.0,
        closed_at=datetime.utcnow(), opened_at=datetime.utcnow() - timedelta(minutes=45),
    )
    n_closed = build_narrative(closed_loss, session)
    check("Closed-loss failure line ties back to premium-zone weakness", "premium" in (n_closed.failure_line or "").lower())
    check("Closed-loss held_duration computed", n_closed.held_duration is not None)
    check("Closed-loss r_multiple is negative", n_closed.r_multiple is not None and n_closed.r_multiple < 0)

    session.close()

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
