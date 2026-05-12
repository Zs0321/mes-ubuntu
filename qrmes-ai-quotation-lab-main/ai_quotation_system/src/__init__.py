"""
AI报价系统 - 源代码包
"""

from .data_analyzer import QuotationDataAnalyzer
from .price_predictor import PricePredictor, QuotationCalculator
from .ai_assistant import QuotationAIAssistant
from .component_cost_engine import (
    ComponentCostEngine,
    CostBreakdown,
    AluminumCastingCalculator,
    AluminumMachiningCalculator,
    StampingCalculator,
    SiliconSteelCalculator,
    MagnetCalculator,
    CopperWindingCalculator,
    ShaftCalculator,
    BearingCalculator,
    PCBACalculator,
    PowerSemiconductorCalculator,
)

__all__ = [
    'QuotationDataAnalyzer',
    'PricePredictor',
    'QuotationCalculator',
    'QuotationAIAssistant',
    'ComponentCostEngine',
    'CostBreakdown',
    'AluminumCastingCalculator',
    'AluminumMachiningCalculator',
    'StampingCalculator',
    'SiliconSteelCalculator',
    'MagnetCalculator',
    'CopperWindingCalculator',
    'ShaftCalculator',
    'BearingCalculator',
    'PCBACalculator',
    'PowerSemiconductorCalculator',
]

__version__ = '1.1.0'
