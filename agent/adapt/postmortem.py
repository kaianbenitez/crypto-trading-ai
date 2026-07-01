from agent.db.models import Trade


def generate_postmortem(trade: Trade) -> list[str]:
    """Plain-English reasoning on why a closed trade won or lost, derived from
    the entry snapshot vs the exit outcome. Used as input to the bounded tuner."""
    notes = []
    snapshot = trade.get_indicator_snapshot()
    entry_reasoning = trade.get_entry_reasoning()

    notes.append(f"Strategy '{trade.strategy_name}' in '{trade.regime}' regime, "
                 f"exited via {trade.exit_reason}, outcome={trade.outcome}.")

    if trade.outcome == "loss":
        if trade.exit_reason == "stop_loss":
            notes.append("Stop-loss was hit before price moved favorably — "
                          "possible causes: stop too tight for current volatility (ATR), "
                          "or entry signal was a false positive.")
            adx = snapshot.get("adx")
            if adx is not None and trade.regime == "trending" and float(adx) < 30:
                notes.append(f"ADX was only {adx} at entry — borderline trend strength, "
                              "regime classification may have been premature.")
            if snapshot.get("vol_confirmed") is False:
                notes.append("Volume confirmation was weak/absent despite signal firing — "
                              "review volume filter strictness.")
        else:
            notes.append("Loss occurred without a clear stop-loss trigger reason logged — "
                          "review exit logic.")
    elif trade.outcome == "win":
        notes.append("Entry conditions were validated by price action — "
                      "reinforces current parameter set for this regime/strategy combo.")

    notes.append(f"Entry reasoning was: {'; '.join(entry_reasoning)}")
    return notes
