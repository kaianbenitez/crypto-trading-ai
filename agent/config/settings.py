import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    # Binance
    binance_api_key: str = os.getenv("BINANCE_API_KEY", "")
    binance_api_secret: str = os.getenv("BINANCE_API_SECRET", "")
    binance_testnet: bool = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

    # Bybit
    bybit_api_key: str = os.getenv("BYBIT_API_KEY", "")
    bybit_api_secret: str = os.getenv("BYBIT_API_SECRET", "")
    bybit_testnet: bool = os.getenv("BYBIT_TESTNET", "true").lower() == "true"

    # Which exchange to use: "binance" or "bybit"
    exchange: str = os.getenv("EXCHANGE", "binance")

    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    telegram_allowed_user_ids: str = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")

    bankroll_usdt: float = float(os.getenv("BANKROLL_USDT", "1000"))

    max_risk_per_trade_pct: float = float(os.getenv("MAX_RISK_PER_TRADE_PCT", "1.5"))
    max_daily_drawdown_pct: float = float(os.getenv("MAX_DAILY_DRAWDOWN_PCT", "5"))
    max_concurrent_positions: int = int(os.getenv("MAX_CONCURRENT_POSITIONS", "1"))
    default_leverage: int = int(os.getenv("DEFAULT_LEVERAGE", "3"))
    max_leverage: int = int(os.getenv("MAX_LEVERAGE", "5"))


settings = Settings()
