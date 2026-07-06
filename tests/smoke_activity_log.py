"""Smoke script for the decision-log observability layer.
Run directly: `python3 tests/smoke_activity_log.py`.

Covers the additive instrumentation only — it must never touch the
entry/exit path:
- _flush_decision_log writes activity + gate rows for a cycle
- _prune_decision_log bounds both tables (row-cap and time-cap)
- /api/gate-stats aggregates per gate over a window, ranked
- /api/activity-log returns newest-first, honours limit + since
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.db.models import get_session, SignalGateEvent, AgentActivityLog  # noqa: E402
import agent.orchestrator as orch  # noqa: E402
from webapi.main import gate_stats, activity_log  # noqa: E402

failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        failures.append(label)


def main():
    session = get_session("sqlite:///:memory:")

    # --- 1. Flush writes both activity and gate rows for a cycle ---
    activity_events = [
        {"symbol": "BTC/USDT", "message": "candidate LONG score=0.80 EV=0.40R", "level": "candidate"},
        {"symbol": "ETH/USDT", "message": "EV 0.10R below cost-aware floor 0.25R", "level": "block"},
        {"symbol": "SOL/USDT", "message": "re-entry blocked (cooldown)", "level": "block"},
        {"symbol": "XRP/USDT", "message": "No trend signal: ADX 12.0 < 20", "level": "info"},
    ]
    gate_events = [
        {"symbol": "ETH/USDT", "gate": "cost_edge", "reason": "EV below floor", "side": "long", "confidence": 0.55},
        {"symbol": "SOL/USDT", "gate": "reentry", "reason": "cooldown", "side": "short", "confidence": 0.60},
        {"symbol": "XRP/USDT", "gate": "no_signal", "reason": "ADX < 20", "side": "none", "confidence": 0.0},
    ]
    orch._flush_decision_log(session, cycle=1, activity_events=activity_events, gate_events=gate_events)

    act_count = session.query(AgentActivityLog).count()
    gate_count = session.query(SignalGateEvent).count()
    check("Activity rows written for the cycle", act_count == 4)
    check("Gate rows written only for rejections", gate_count == 3)

    # A second cycle with another cost_edge rejection (to test ranking).
    orch._flush_decision_log(
        session, cycle=2,
        activity_events=[{"symbol": "BNB/USDT", "message": "cost/edge gate (net EV)", "level": "block"}],
        gate_events=[{"symbol": "BNB/USDT", "gate": "cost_edge", "reason": "net EV", "side": "long", "confidence": 0.5}],
    )

    # --- 2. Empty flush is a no-op, never raises ---
    before = session.query(AgentActivityLog).count()
    orch._flush_decision_log(session, cycle=3, activity_events=[], gate_events=[])
    check("Empty flush is a harmless no-op", session.query(AgentActivityLog).count() == before)

    # --- 3. gate-stats aggregates + ranks by count over the window ---
    stats = gate_stats(window="24h", session=session, _=None)
    check("gate-stats total equals gate rows", stats["total"] == 4)
    top = stats["gates"][0]
    check("Most-rejecting gate ranked first (cost_edge x2)", top["gate"] == "cost_edge" and top["count"] == 2)
    check("gate-stats attaches human labels", all(g.get("label") for g in stats["gates"]))
    check("Unknown window falls back to 24h", gate_stats(window="bogus", session=session, _=None)["window"] == "24h")

    # --- 4. activity-log newest-first + limit + since ---
    rows = activity_log(limit=200, since=None, session=session, _=None)
    check("activity-log returns all rows", len(rows) == 5)
    check("activity-log is newest-first (BNB cycle 2 first)", rows[0]["symbol"] == "BNB/USDT")
    check("activity-log honours limit", len(activity_log(limit=2, since=None, session=session, _=None)) == 2)

    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    check("since in the future returns nothing", activity_log(limit=200, since=future, session=session, _=None) == [])
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    check("since in the past returns rows", len(activity_log(limit=200, since=past, session=session, _=None)) == 5)

    # --- 5. Prune: row cap (monkeypatch the constant to something small) ---
    orig_rows = orch._ACTIVITY_MAX_ROWS
    orch._ACTIVITY_MAX_ROWS = 2
    try:
        orch._prune_decision_log(session)
        check("Activity log pruned down to the row cap", session.query(AgentActivityLog).count() == 2)
        remaining = activity_log(limit=200, since=None, session=session, _=None)
        check("Prune keeps the newest rows", remaining[0]["symbol"] == "BNB/USDT")
    finally:
        orch._ACTIVITY_MAX_ROWS = orig_rows

    # --- 6. Prune: time cap removes old gate events ---
    old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=orch._GATE_MAX_DAYS + 5)
    session.add(SignalGateEvent(symbol="OLD/USDT", gate="mtf", reason="stale", created_at=old))
    session.commit()
    orch._prune_decision_log(session)
    check("Old gate events pruned past the time window",
          session.query(SignalGateEvent).filter(SignalGateEvent.symbol == "OLD/USDT").count() == 0)
    check("Recent gate events survive pruning", session.query(SignalGateEvent).count() >= 1)

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
