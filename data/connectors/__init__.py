from .base import Connector
from .yfinance_adapter import get_candles as yfinance_get_candles
from .binance_adapter import get_candles as binance_get_candles
from .bybit_adapter import get_candles as bybit_get_candles
from .okx_adapter import get_candles as okx_get_candles
from .coinbase_adapter import get_candles as coinbase_get_candles
from .kraken_adapter import get_candles as kraken_get_candles
from .kucoin_adapter import get_candles as kucoin_get_candles
from .cryptocompare_adapter import (
	cryptocompare_get_candles_sync as cryptocompare_get_candles,
	cryptocompare_get_candles as cryptocompare_get_candles_async,
)
from .twelvedata_adapter import get_candles as twelvedata_get_candles
from .polygon_adapter import get_candles as polygon_get_candles
from .tiingo_adapter import get_candles as tiingo_get_candles
from .fmp_adapter import get_candles as fmp_get_candles
from .ecb_adapter import get_candles as ecb_get_candles
from .alphavantage_adapter import get_candles as alphavantage_get_candles
from .oanda_adapter import get_candles as oanda_get_candles

__all__ = [
	"Connector",
	"yfinance_get_candles",
	"binance_get_candles",
	"bybit_get_candles",
	"okx_get_candles",
	"coinbase_get_candles",
	"kraken_get_candles",
	"kucoin_get_candles",
	"cryptocompare_get_candles",
	"cryptocompare_get_candles_async",
	"twelvedata_get_candles",
	"polygon_get_candles",
	"tiingo_get_candles",
	"fmp_get_candles",
	"ecb_get_candles",
	"alphavantage_get_candles",
	"oanda_get_candles",
]
