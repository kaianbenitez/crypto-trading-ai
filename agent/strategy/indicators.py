import pandas as pd
import ta


def add_indicators(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """df must have columns: open, high, low, close, volume. Returns df with indicators added."""
    out = df.copy()

    out["ema_fast"] = ta.trend.ema_indicator(out["close"], window=params.get("ema_fast", 12))
    out["ema_slow"] = ta.trend.ema_indicator(out["close"], window=params.get("ema_slow", 26))

    macd = ta.trend.MACD(
        out["close"],
        window_fast=params.get("macd_fast", 12),
        window_slow=params.get("macd_slow", 26),
        window_sign=params.get("macd_signal", 9),
    )
    out["macd"] = macd.macd()
    out["macd_signal"] = macd.macd_signal()
    out["macd_hist"] = macd.macd_diff()

    out["rsi"] = ta.momentum.rsi(out["close"], window=params.get("rsi_period", 14))

    bb = ta.volatility.BollingerBands(out["close"], window=params.get("bb_period", 20), window_dev=params.get("bb_std", 2))
    out["bb_upper"] = bb.bollinger_hband()
    out["bb_lower"] = bb.bollinger_lband()
    out["bb_mid"] = bb.bollinger_mavg()

    out["atr"] = ta.volatility.average_true_range(
        out["high"], out["low"], out["close"], window=params.get("atr_period", 14)
    )

    out["adx"] = ta.trend.adx(out["high"], out["low"], out["close"], window=params.get("adx_period", 14))

    out["vol_sma"] = out["volume"].rolling(params.get("vol_sma_period", 20)).mean()
    out["vol_confirmed"] = out["volume"] > out["vol_sma"] * params.get("vol_confirm_mult", 1.0)

    return out
