import unittest
from pownet.optim_model import objfunc


class TestObjectiveFunctions(unittest.TestCase):

    def setUp(self):
        """Set up common test data."""
        self.timesteps = range(3)  # As per user request
        self.thermal_units = ["coal_unit_1", "gas_unit_1"]
        self.nondispatch_units = ["hydro_1", "solar_1"]

    def test_get_thermal_fixed_coeff(self):
        thermal_rated_capacity = {"coal_unit_1": 300, "gas_unit_1": 150}
        thermal_fixed_cost = {"coal_unit_1": 10, "gas_unit_1": 12}

        expected_coeffs = {
            ("coal_unit_1", 0): 300 * 10,
            ("coal_unit_1", 1): 300 * 10,
            ("coal_unit_1", 2): 300 * 10,
            ("gas_unit_1", 0): 150 * 12,
            ("gas_unit_1", 1): 150 * 12,
            ("gas_unit_1", 2): 150 * 12,
        }

        actual_coeffs = objfunc.get_thermal_fixed_coeff(
            timesteps=self.timesteps,
            thermal_units=self.thermal_units,
            thermal_fixed_cost=thermal_fixed_cost,
            thermal_rated_capacity=thermal_rated_capacity,
        )
        self.assertEqual(actual_coeffs, expected_coeffs)

    def test_get_thermal_opex_coeff_step_1(self):
        step_k = 1
        thermal_opex = {"coal_unit_1": 5, "gas_unit_1": 3}
        fuel_contracts = {"coal_unit_1": "coal_A", "gas_unit_1": "gas_B"}
        # contract_costs: (fuel_type, time_index) -> cost
        contract_costs = {
            ("coal_A", 0): 20,
            ("coal_A", 1): 21,
            ("coal_A", 2): 20,
            ("coal_A", 24): 25,
            ("gas_B", 0): 30,
            ("gas_B", 1): 32,
            ("gas_B", 2): 31,
            ("gas_B", 24): 35,
        }
        thermal_heat_rate = {"coal_unit_1": 1.5, "gas_unit_1": 1.2}

        expected_coeffs = {
            # (unit, t): (contract_costs[(fuel_contracts[unit], t + (step_k - 1) * 24)] * thermal_heat_rate[unit]) + thermal_opex[unit]
            ("coal_unit_1", 0): (contract_costs[("coal_A", 0 + (1 - 1) * 24)] * 1.5)
            + 5,  # (20 * 1.5) + 5 = 30 + 5 = 35
            ("coal_unit_1", 1): (contract_costs[("coal_A", 1 + (1 - 1) * 24)] * 1.5)
            + 5,  # (21 * 1.5) + 5 = 31.5 + 5 = 36.5
            ("coal_unit_1", 2): (contract_costs[("coal_A", 2 + (1 - 1) * 24)] * 1.5)
            + 5,  # (20 * 1.5) + 5 = 30 + 5 = 35
            ("gas_unit_1", 0): (contract_costs[("gas_B", 0 + (1 - 1) * 24)] * 1.2)
            + 3,  # (30 * 1.2) + 3 = 36 + 3 = 39
            ("gas_unit_1", 1): (contract_costs[("gas_B", 1 + (1 - 1) * 24)] * 1.2)
            + 3,  # (32 * 1.2) + 3 = 38.4 + 3 = 41.4
            ("gas_unit_1", 2): (contract_costs[("gas_B", 2 + (1 - 1) * 24)] * 1.2)
            + 3,  # (31 * 1.2) + 3 = 37.2 + 3 = 40.2
        }

        actual_coeffs = objfunc.get_thermal_opex_coeff(
            step_k=step_k,
            timesteps=self.timesteps,
            thermal_units=self.thermal_units,
            thermal_opex=thermal_opex,
            fuel_contracts=fuel_contracts,
            contract_costs=contract_costs,
            thermal_heat_rate=thermal_heat_rate,
        )
        self.assertEqual(actual_coeffs, expected_coeffs)

    def test_get_thermal_opex_coeff_step_2(self):
        step_k = 2  # Test with a different step_k
        thermal_opex = {"coal_unit_1": 5, "gas_unit_1": 3}
        fuel_contracts = {"coal_unit_1": "coal_A", "gas_unit_1": "gas_B"}
        contract_costs = {
            # Need costs for t + (2-1)*24 => t + 24
            ("coal_A", 24): 25,
            ("coal_A", 25): 26,
            ("coal_A", 26): 24,
            ("gas_B", 24): 35,
            ("gas_B", 25): 36,
            ("gas_B", 26): 34,
        }
        thermal_heat_rate = {"coal_unit_1": 1.5, "gas_unit_1": 1.2}

        expected_coeffs = {
            ("coal_unit_1", 0): (contract_costs[("coal_A", 0 + (2 - 1) * 24)] * 1.5)
            + 5,  # (25 * 1.5) + 5 = 37.5 + 5 = 42.5
            ("coal_unit_1", 1): (contract_costs[("coal_A", 1 + (2 - 1) * 24)] * 1.5)
            + 5,  # (26 * 1.5) + 5 = 39 + 5 = 44
            ("coal_unit_1", 2): (contract_costs[("coal_A", 2 + (2 - 1) * 24)] * 1.5)
            + 5,  # (24 * 1.5) + 5 = 36 + 5 = 41
            ("gas_unit_1", 0): (contract_costs[("gas_B", 0 + (2 - 1) * 24)] * 1.2)
            + 3,  # (35 * 1.2) + 3 = 42 + 3 = 45
            ("gas_unit_1", 1): (contract_costs[("gas_B", 1 + (2 - 1) * 24)] * 1.2)
            + 3,  # (36 * 1.2) + 3 = 43.2 + 3 = 46.2
            ("gas_unit_1", 2): (contract_costs[("gas_B", 2 + (2 - 1) * 24)] * 1.2)
            + 3,  # (34 * 1.2) + 3 = 40.8 + 3 = 43.8
        }

        actual_coeffs = objfunc.get_thermal_opex_coeff(
            step_k=step_k,
            timesteps=self.timesteps,
            thermal_units=self.thermal_units,
            thermal_opex=thermal_opex,
            fuel_contracts=fuel_contracts,
            contract_costs=contract_costs,
            thermal_heat_rate=thermal_heat_rate,
        )
        self.assertEqual(actual_coeffs, expected_coeffs)

    def test_get_thermal_startup_coeff(self):
        thermal_rated_capacity = {"coal_unit_1": 300, "gas_unit_1": 150}
        thermal_startup_cost = {
            "coal_unit_1": 500,
            "gas_unit_1": 250,
        }  # Cost per unit of capacity

        expected_coeffs = {
            ("coal_unit_1", 0): 300 * 500,
            ("coal_unit_1", 1): 300 * 500,
            ("coal_unit_1", 2): 300 * 500,
            ("gas_unit_1", 0): 150 * 250,
            ("gas_unit_1", 1): 150 * 250,
            ("gas_unit_1", 2): 150 * 250,
        }
        actual_coeffs = objfunc.get_thermal_startup_coeff(
            timesteps=self.timesteps,
            thermal_units=self.thermal_units,
            thermal_startup_cost=thermal_startup_cost,
            thermal_rated_capacity=thermal_rated_capacity,
        )
        self.assertEqual(actual_coeffs, expected_coeffs)

    def test_get_marginal_cost_coeff_step_1(self):
        step_k = 1
        nondispatch_contracts = {"hydro_1": "hydro_A", "solar_1": "solar_B"}
        # contract_costs: (contract_name, time_index) -> cost
        contract_costs = {
            ("hydro_A", 0): 5,
            ("hydro_A", 1): 5.5,
            ("hydro_A", 2): 5.2,
            ("hydro_A", 24): 6,
            ("solar_B", 0): 2,
            ("solar_B", 1): 2.1,
            ("solar_B", 2): 2.0,
            ("solar_B", 24): 2.5,
        }
        expected_coeffs = {
            # (unit, t): contract_costs[(nondispatch_contracts[unit], t + (step_k - 1) * 24)]
            ("hydro_1", 0): contract_costs[("hydro_A", 0 + (1 - 1) * 24)],  # 5
            ("hydro_1", 1): contract_costs[("hydro_A", 1 + (1 - 1) * 24)],  # 5.5
            ("hydro_1", 2): contract_costs[("hydro_A", 2 + (1 - 1) * 24)],  # 5.2
            ("solar_1", 0): contract_costs[("solar_B", 0 + (1 - 1) * 24)],  # 2
            ("solar_1", 1): contract_costs[("solar_B", 1 + (1 - 1) * 24)],  # 2.1
            ("solar_1", 2): contract_costs[("solar_B", 2 + (1 - 1) * 24)],  # 2.0
        }
        actual_coeffs = objfunc.get_marginal_cost_coeff(
            step_k=step_k,
            timesteps=self.timesteps,
            units=self.nondispatch_units,
            nondispatch_contracts=nondispatch_contracts,
            contract_costs=contract_costs,
        )
        self.assertEqual(actual_coeffs, expected_coeffs)

    def test_get_marginal_cost_coeff_step_2(self):
        step_k = 2  # Test with a different step_k
        nondispatch_contracts = {"hydro_1": "hydro_A", "solar_1": "solar_B"}
        contract_costs = {
            # Need costs for t + (2-1)*24 => t + 24
            ("hydro_A", 24): 6,
            ("hydro_A", 25): 6.5,
            ("hydro_A", 26): 6.2,
            ("solar_B", 24): 3,
            ("solar_B", 25): 3.1,
            ("solar_B", 26): 3.0,
        }
        expected_coeffs = {
            ("hydro_1", 0): contract_costs[("hydro_A", 0 + (2 - 1) * 24)],  # 6
            ("hydro_1", 1): contract_costs[("hydro_A", 1 + (2 - 1) * 24)],  # 6.5
            ("hydro_1", 2): contract_costs[("hydro_A", 2 + (2 - 1) * 24)],  # 6.2
            ("solar_1", 0): contract_costs[("solar_B", 0 + (2 - 1) * 24)],  # 3
            ("solar_1", 1): contract_costs[("solar_B", 1 + (2 - 1) * 24)],  # 3.1
            ("solar_1", 2): contract_costs[("solar_B", 2 + (2 - 1) * 24)],  # 3.0
        }
        actual_coeffs = objfunc.get_marginal_cost_coeff(
            step_k=step_k,
            timesteps=self.timesteps,
            units=self.nondispatch_units,
            nondispatch_contracts=nondispatch_contracts,
            contract_costs=contract_costs,
        )
        self.assertEqual(actual_coeffs, expected_coeffs)


if __name__ == "__main__":
    unittest.main()
