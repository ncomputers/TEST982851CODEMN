import os
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()


# API credentials for Delta Exchange
API_KEY = os.getenv('DELTA_API_KEY', 'sUABSFPLpe5QNVJuKsOL6O0r5TiUoP')
API_SECRET = os.getenv('DELTA_API_SECRET', 'Q6Fo1NcOtNIxJZ9IPRUxROcSZ4vQdI31hDVPaoOvJnYfPt5wQLaNb6WMnNOy')

# Delta Exchange API endpoints
DELTA_API_URLS = {
    'public': os.getenv('DELTA_PUBLIC_URL', 'https://api.india.delta.exchange'),
    'private': os.getenv('DELTA_PRIVATE_URL', 'https://api.india.delta.exchange'),
}
FIXED_OFFSET = int(os.getenv('FIXED_OFFSET', 0))

# Trading parameters
DEFAULT_ORDER_TYPE = 'limit'
TRAILING_STOP_PERCENT = 2.0  # 2% trailing stop
BASKET_ORDER_ENABLED = True

# Logging configuration
LOG_FILE = os.getenv('LOG_FILE', 'trading.log')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'DEBUG')

# Redis configuration
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_DB = int(os.getenv('REDIS_DB', '0'))

# Market data caching TTL (in seconds)
MARKET_CACHE_TTL = int(os.getenv('MARKET_CACHE_TTL', '300'))

# Database configuration (if needed)
DATABASE_URI = os.getenv('DATABASE_URI', 'sqlite:///trading.db')


# Profit trailing configuration
PROFIT_TRAILING_CONFIG = {
    "start_trailing_profit_pct": 0.005,  # trailing starts at 0.5% profit
    "levels": [
         {"min_profit_pct": 0.005, "trailing_stop_offset": 0.001, "book_fraction": 1.0},   # 0.5%-1%: stop = entry*(1+0.001)
         {"min_profit_pct": 0.01,  "trailing_stop_offset": 0.006, "book_fraction": 1.0},    # 1%-1.5%: stop = entry*(1+0.006)
         {"min_profit_pct": 0.015, "trailing_stop_offset": 0.012, "book_fraction": 1.0},    # 1.5%-2%: stop = entry*(1+0.012)
         {"min_profit_pct": 0.02,  "trailing_stop_offset": None, "book_fraction": 0.9}       # ≥2%: partial booking mode; new stop = entry*(1+profit_pct*0.9)
    ],
    "fixed_stop_loss_pct": 0.005,  # fixed stop loss at 0.5% adverse movement
    "trailing_unit": "percent"
}
