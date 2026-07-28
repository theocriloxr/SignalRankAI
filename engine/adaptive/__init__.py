from .elliott import ElliottWaveComponent
from .fibonacci import FibonacciComponent
from .harmonic import HarmonicComponent
from .ict_smc import ICTSmartMoneyComponent
from .indicators import IndicatorComponent
from .order_flow import OrderFlowComponent
from .price_action import PriceActionComponent
from .supply_demand import SupplyDemandComponent
from .wyckoff import WyckoffComponent

DEFAULT_COMPONENTS = (
    ICTSmartMoneyComponent(), PriceActionComponent(), SupplyDemandComponent(),
    FibonacciComponent(), HarmonicComponent(), ElliottWaveComponent(),
    OrderFlowComponent(), WyckoffComponent(), IndicatorComponent(),
)
