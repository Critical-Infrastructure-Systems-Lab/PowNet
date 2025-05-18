import unittest
import gurobipy as gp


from pownet.optim_model.constraints import energy_storage_constr


class TestEnergyStorageConstraints(unittest.TestCase):
    """Test cases for energy storage unit constraints."""

    def setUp(self):
        """Set up common resources for each test method."""
        self.model = gp.Model("test_energy_storage_constraints")
        self.model.setParam("OutputFlag", 0)  # Suppress Gurobi output

        self.timesteps = range(1, 4)  # Timesteps: 1, 2, 3
        self.sim_horizon = 3  # Corresponds to the end of self.timesteps
        self.storage_units = ["ESS1", "ESS2"]

        self.max_charge_cap = {
            unit: 50.0 + idx * 10 for idx, unit in enumerate(self.storage_units)
        }
        self.max_discharge_cap = {
            unit: 40.0 + idx * 10 for idx, unit in enumerate(self.storage_units)
        }

        self.charge_state_init = {
            unit: 100.0 + idx * 20 for idx, unit in enumerate(self.storage_units)
        }
        self.charge_efficiency = {
            unit: 0.95 - idx * 0.02 for idx, unit in enumerate(self.storage_units)
        }
        # Ensure discharge_efficiency is not zero
        self.discharge_efficiency = {
            unit: 0.90 - idx * 0.02 for idx, unit in enumerate(self.storage_units)
        }
        self.self_discharge_rate = {
            unit: 0.01 + idx * 0.005 for idx, unit in enumerate(self.storage_units)
        }

        # Variables
        self.pcharge = self.model.addVars(
            self.storage_units, self.timesteps, vtype=gp.GRB.CONTINUOUS, name="pcharge"
        )
        self.ucharge = self.model.addVars(
            self.storage_units, self.timesteps, vtype=gp.GRB.BINARY, name="ucharge"
        )
        self.pdischarge = self.model.addVars(
            self.storage_units,
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            name="pdischarge",
        )
        self.udischarge = self.model.addVars(
            self.storage_units, self.timesteps, vtype=gp.GRB.BINARY, name="udischarge"
        )
        self.charge_state = self.model.addVars(
            self.storage_units,
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            name="charge_state",
        )

        self.model.update()

    def tearDown(self):
        """Clean up resources after each test method."""
        self.model.dispose()

    def _check_constr_details(
        self,
        constr_name_base,
        constr_dict,
        expected_keys_iterable,
        expected_sense,
        get_expected_rhs_func,
        get_expected_lhs_coeffs_func,
    ):
        """Helper to check constraint details."""
        self.assertEqual(len(constr_dict), len(list(expected_keys_iterable)))

        for key_tuple in expected_keys_iterable:
            # Construct the full constraint name as Gurobi creates it
            if isinstance(key_tuple, str):  # Single key for some constraints
                full_constr_name = f"{constr_name_base}[{key_tuple}]"
                key_for_data = key_tuple  # used for fetching data from dicts
            else:  # Multiple keys (unit, t)
                full_constr_name = (
                    f"{constr_name_base}[{','.join(map(str, key_tuple))}]"
                )
                key_for_data = key_tuple

            current_constr = self.model.getConstrByName(full_constr_name)
            self.assertIsNotNone(
                current_constr, f"Constraint {full_constr_name} not found."
            )

            self.assertEqual(
                current_constr.Sense,
                expected_sense,
                f"Sense mismatch for {full_constr_name}",
            )

            expected_rhs = get_expected_rhs_func(key_for_data)
            self.assertAlmostEqual(
                current_constr.RHS,
                expected_rhs,
                msg=f"RHS mismatch for {full_constr_name}",
            )

            row = self.model.getRow(current_constr)
            expected_lhs_coeffs = get_expected_lhs_coeffs_func(key_for_data)

            actual_coeffs = {
                row.getVar(i).VarName: row.getCoeff(i) for i in range(row.size())
            }
            self.assertEqual(
                row.size(),
                len(expected_lhs_coeffs),
                f"LHS term count mismatch for {full_constr_name}",
            )
            self.assertDictEqual(
                actual_coeffs,
                expected_lhs_coeffs,
                f"LHS coeffs mismatch for {full_constr_name}",
            )

    def test_add_c_link_ess_charge(self):
        constrs = energy_storage_constr.add_c_link_ess_charge(
            self.model,
            self.pcharge,
            self.ucharge,
            self.timesteps,
            self.storage_units,
            self.max_charge_cap,
        )
        self.model.update()

        def get_rhs(key):  # key is (unit, t)
            return 0.0

        def get_lhs(key):  # key is (unit, t)
            unit, t = key
            return {
                self.pcharge[unit, t].VarName: 1.0,
                self.ucharge[unit, t].VarName: -self.max_charge_cap[unit],
            }

        expected_keys = [(u, t) for u in self.storage_units for t in self.timesteps]
        self._check_constr_details(
            "link_ess_charge",
            constrs,
            expected_keys,
            gp.GRB.LESS_EQUAL,
            get_rhs,
            get_lhs,
        )

        # Test with empty units
        empty_constrs = energy_storage_constr.add_c_link_ess_charge(
            self.model,
            self.pcharge,
            self.ucharge,
            self.timesteps,
            [],
            self.max_charge_cap,
        )
        self.assertEqual(len(empty_constrs), 0)

    def test_add_c_link_ess_discharge(self):
        constrs = energy_storage_constr.add_c_link_ess_discharge(
            self.model,
            self.pdischarge,
            self.udischarge,
            self.timesteps,
            self.storage_units,
            self.max_discharge_cap,
        )
        self.model.update()

        def get_rhs(key):  # key is (unit, t)
            return 0.0

        def get_lhs(key):  # key is (unit, t)
            unit, t = key
            return {
                self.pdischarge[unit, t].VarName: 1.0,
                self.udischarge[unit, t].VarName: -self.max_discharge_cap[unit],
            }

        expected_keys = [(u, t) for u in self.storage_units for t in self.timesteps]
        self._check_constr_details(
            "link_ess_discharge",
            constrs,
            expected_keys,
            gp.GRB.LESS_EQUAL,
            get_rhs,
            get_lhs,
        )

        # Test with empty units
        empty_constrs = energy_storage_constr.add_c_link_ess_discharge(
            self.model,
            self.pdischarge,
            self.udischarge,
            self.timesteps,
            [],
            self.max_discharge_cap,
        )
        self.assertEqual(len(empty_constrs), 0)

    def test_add_c_link_ess_state(self):
        constrs = energy_storage_constr.add_c_link_ess_state(
            self.model,
            self.ucharge,
            self.udischarge,
            self.timesteps,
            self.storage_units,
        )
        self.model.update()

        def get_rhs(key):  # key is (unit, t)
            return 1.0

        def get_lhs(key):  # key is (unit, t)
            unit, t = key
            return {
                self.ucharge[unit, t].VarName: 1.0,
                self.udischarge[unit, t].VarName: 1.0,
            }

        expected_keys = [(u, t) for u in self.storage_units for t in self.timesteps]
        self._check_constr_details(
            "link_ess_state",
            constrs,
            expected_keys,
            gp.GRB.LESS_EQUAL,
            get_rhs,
            get_lhs,
        )

        # Test with empty units
        empty_constrs = energy_storage_constr.add_c_link_ess_state(
            self.model, self.ucharge, self.udischarge, self.timesteps, []
        )
        self.assertEqual(len(empty_constrs), 0)

    def test_add_c_unit_ess_balance_init(self):
        # Fixed t=1
        t_init = 1
        constrs = energy_storage_constr.add_c_unit_ess_balance_init(
            self.model,
            self.pcharge,
            self.pdischarge,
            self.charge_state,
            self.storage_units,
            self.charge_state_init,
            self.charge_efficiency,
            self.discharge_efficiency,
            self.self_discharge_rate,
        )
        self.model.update()

        def get_rhs(unit):  # key is unit
            return (1 - self.self_discharge_rate[unit]) * self.charge_state_init[unit]

        def get_lhs(unit):  # key is unit
            # charge_state[u,1] - CE[u]*pcharge[u,1] + (1/DE[u])*pdischarge[u,1] == RHS
            return {
                self.charge_state[unit, t_init].VarName: 1.0,
                self.pcharge[unit, t_init].VarName: -self.charge_efficiency[unit],
                self.pdischarge[unit, t_init].VarName: 1.0
                / self.discharge_efficiency[unit],
            }

        # For this constraint, keys are just units as t is fixed to 1 inside the function
        expected_keys = [u for u in self.storage_units]
        self._check_constr_details(
            "unit_ess_balance_init",
            constrs,
            expected_keys,
            gp.GRB.EQUAL,
            get_rhs,
            get_lhs,
        )

        # Test with empty units
        empty_constrs = energy_storage_constr.add_c_unit_ess_balance_init(
            self.model,
            self.pcharge,
            self.pdischarge,
            self.charge_state,
            [],
            self.charge_state_init,
            self.charge_efficiency,
            self.discharge_efficiency,
            self.self_discharge_rate,
        )
        self.assertEqual(len(empty_constrs), 0)

    def test_add_c_unit_ess_balance(self):
        constrs = energy_storage_constr.add_c_unit_ess_balance(
            self.model,
            self.pcharge,
            self.pdischarge,
            self.charge_state,
            self.storage_units,
            self.sim_horizon,
            self.charge_efficiency,
            self.discharge_efficiency,
            self.self_discharge_rate,
        )
        self.model.update()

        def get_rhs(key):  # key is (unit, t)
            return 0.0

        def get_lhs(key):  # key is (unit, t)
            unit, t = key
            # CS[u,t] - (1-SDR[u])*CS[u,t-1] - CE[u]*Pch[u,t] + (1/DE[u])*Pdch[u,t] == 0
            return {
                self.charge_state[unit, t].VarName: 1.0,
                self.charge_state[unit, t - 1].VarName: -(
                    1 - self.self_discharge_rate[unit]
                ),
                self.pcharge[unit, t].VarName: -self.charge_efficiency[unit],
                self.pdischarge[unit, t].VarName: 1.0 / self.discharge_efficiency[unit],
            }

        # Constraints are for t = 2 to sim_horizon
        expected_keys = [
            (u, t) for u in self.storage_units for t in range(2, self.sim_horizon + 1)
        ]
        self._check_constr_details(
            "unit_ess_balance", constrs, expected_keys, gp.GRB.EQUAL, get_rhs, get_lhs
        )

        # Test with sim_horizon = 1 (should add no constraints)
        constrs_horizon1 = energy_storage_constr.add_c_unit_ess_balance(
            self.model,
            self.pcharge,
            self.pdischarge,
            self.charge_state,
            self.storage_units,
            1,
            self.charge_efficiency,  # sim_horizon = 1
            self.discharge_efficiency,
            self.self_discharge_rate,
        )
        self.assertEqual(len(constrs_horizon1), 0)

        # Test with empty units
        empty_constrs = energy_storage_constr.add_c_unit_ess_balance(
            self.model,
            self.pcharge,
            self.pdischarge,
            self.charge_state,
            [],
            self.sim_horizon,
            self.charge_efficiency,
            self.discharge_efficiency,
            self.self_discharge_rate,
        )
        self.assertEqual(len(empty_constrs), 0)


if __name__ == "__main__":
    unittest.main()
