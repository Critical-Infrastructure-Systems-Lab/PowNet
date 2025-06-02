"""power_power.py: PowerSystemCoupler facilitates the electricity trading among power systems."""

from ..core.model_builder import ModelBuilder


import logging
logger = logging.getLogger(__name__)


def calculate_system_cost() -> float:
    return 0.0


class PowerPowerCoupler:
    def __init__(self, model_builders: list[ModelBuilder]) -> None:
        self.model_builders: dict[str, ModelBuilder] = {
            model_builder.inputs.model_name: model_builder
            for model_builder in model_builders
        }

        # Locational marginal prices (LMPs) in the format {node_id: lmp_value}
        self.lmps: dict[str, float] = {}

        # Trade forward variables
        best_allowed_trade_fwd = {}
        best_allowed_trade_bwd = {}

        # Trade backward variables

    def initialize(self):
        pass

    def get_trade_variables(self):
        pass

    def _update_model_trade_constraints(self):
        pass

    def _update_model_objective(self):
        pass

    def _optimize_models(self):
        pass

    def _record_results(self):
        pass

    def _update_models(self):
        pass

    def _reset_models(self):
        # Do we even need this as we want to benefit from warm starts?
        pass

    def run(
        self,
        learning_rate: float = 0.1,
        max_iterations: int = 100,
        deviation_threshold: float = 1e-4,
    ):
        pass
