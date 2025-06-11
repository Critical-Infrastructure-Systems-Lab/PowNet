import unittest
import gurobipy as gp
import pandas as pd

from pownet.optim_model.constraints.nondispatch_constr import (
    add_c_hourly_unit_ub,
    add_c_link_unit_pu,
    add_c_hydro_limit_daily,
    add_c_hydro_limit_daily_dict,
    add_c_hydro_limit_weekly,
)


class TestNondispatchConstraints(unittest.TestCase):
    """Test cases for non-dispatchable unit constraints."""

    def setUp(self):
        """Set up common resources for each test method."""
        self.model = gp.Model("test_nondispatch_constraints")
        self.model.setParam("OutputFlag", 0)  # Suppress Gurobi output

        # Define common dimensions and units
        self.timesteps_hourly = range(1, 5)  # 4 hours
        self.timesteps_daily = range(1, 25)  # 24 hours

        # Max horizon needed for phydro is 336 (for 2 weeks test)
        # So define variables up to this horizon if they might be accessed.
        self.max_test_horizon = 336
        self.timesteps_for_setup = range(
            1, self.max_test_horizon + 1
        )  # Timesteps 1 to 336

        self.wind_units = ["W1", "W2"]
        self.solar_units = ["S1"]
        self.hydro_units = ["H1", "H2"]
        self.import_units = ["I1"]

        self.all_units = (
            self.wind_units + self.solar_units + self.hydro_units + self.import_units
        )

        self.contracted_capacity_dict = {
            "W1": 50.0,
            "W2": 75.0,
            "S1": 100.0,
            "H1": 120.0,
            "H2": 80.0,
            "I1": 200.0,
        }

        # Variables
        # pdispatch and u_status are tested with timesteps_hourly (max 4).
        # Defining them up to 168 (original self.timesteps_weekly) or 336 is fine.

        self.pdispatch = self.model.addVars(
            self.all_units,
            self.timesteps_for_setup,
            vtype=gp.GRB.CONTINUOUS,
            name="pdispatch",
        )
        self.u_status = self.model.addVars(
            self.all_units,
            self.timesteps_for_setup,
            vtype=gp.GRB.BINARY,
            name="u_status",
        )

        self.phydro = self.model.addVars(
            self.hydro_units,
            self.timesteps_for_setup,
            vtype=gp.GRB.CONTINUOUS,
            name="phydro",
        )

        # Data for hydro constraints
        self.step_k_daily = 1
        self.sim_horizon_daily = 24  # 1 day
        self.sim_horizon_2days = 48  # 2 days
        self.sim_horizon_weekly = 168  # 1 week
        self.sim_horizon_2weeks = 336  # 2 weeks

        # hydro_capacity for add_c_hydro_limit_daily (DataFrame)
        # Ensure indices for these DataFrames cover the 'week' or 'day' indices accessed.
        # The 'week' index in hydro_capacity_df is step_k + week_offset.
        # Max week_offset for 2 weeks (step_k=1) is 1. So max week_idx_in_df is 1+1=2.
        # DataFrames should have indices at least up to 2.

        days_daily_max_idx = (
            self.step_k_daily + (self.sim_horizon_2days // 24) - 1
        )  # max day index needed
        all_test_days = range(self.step_k_daily, days_daily_max_idx + 1)

        self.hydro_capacity_df_daily = pd.DataFrame(
            {
                unit: [
                    1000.0 + d * 10
                    for d in range(
                        self.step_k_daily,
                        (self.step_k_daily + self.sim_horizon_daily // 24),
                    )
                ]
                for unit in self.hydro_units
            },
            index=range(
                self.step_k_daily, (self.step_k_daily + self.sim_horizon_daily // 24)
            ),
        )
        self.hydro_capacity_df_2days = pd.DataFrame(
            {
                unit: [
                    1000.0 + d_val * 10 + (idx * 5)
                    for idx, d_val in enumerate(
                        range(
                            self.step_k_daily,
                            (self.step_k_daily + self.sim_horizon_2days // 24),
                        )
                    )
                ]
                for unit in self.hydro_units
            },
            index=range(
                self.step_k_daily, (self.step_k_daily + self.sim_horizon_2days // 24)
            ),
        )

        self.hydro_capacity_dict_daily = {
            (unit, day): 1100.0 + day * 5
            for unit in self.hydro_units
            for day in range(
                self.step_k_daily, (self.step_k_daily + self.sim_horizon_daily // 24)
            )
        }
        self.hydro_capacity_dict_2days = {
            (unit, day_val): 1100.0 + day_val * 5 + (idx * 7)
            for idx, day_val in enumerate(
                range(
                    self.step_k_daily,
                    (self.step_k_daily + self.sim_horizon_2days // 24),
                )
            )
            for unit in self.hydro_units
        }

        max_week_idx_for_data = self.step_k_daily + (self.sim_horizon_2weeks // 168) - 1
        all_test_weeks_indices = range(self.step_k_daily, max_week_idx_for_data + 1)

        self.hydro_capacity_weekly_df = pd.DataFrame(
            {
                unit: [7000.0 + w * 100 for w in all_test_weeks_indices]
                for unit in self.hydro_units
            },
            index=all_test_weeks_indices,
        )
        self.hydro_capacity_min_weekly_df = pd.DataFrame(
            {
                unit: [700.0 + w * 10 for w in all_test_weeks_indices]
                for unit in self.hydro_units
            },
            index=all_test_weeks_indices,
        )
        self.hydro_capacity_2weeks_df = (
            pd.DataFrame(  # This was used in the failing test
                {
                    unit: [
                        7000.0 + w_val * 100 + (idx * 50)
                        for idx, w_val in enumerate(all_test_weeks_indices)
                    ]
                    for unit in self.hydro_units
                },
                index=all_test_weeks_indices,
            )
        )
        self.hydro_capacity_min_2weeks_df = (
            pd.DataFrame(  # This was used in the failing test
                {
                    unit: [
                        700.0 + w_val * 10 + (idx * 5)
                        for idx, w_val in enumerate(all_test_weeks_indices)
                    ]
                    for unit in self.hydro_units
                },
                index=all_test_weeks_indices,
            )
        )
        self.model.update()

    def tearDown(self):
        """Clean up resources after each test method."""
        self.model.dispose()

    def _check_constr_details(
        self, constr, expected_sense, expected_rhs, expected_lhs_terms_coeffs
    ):
        """Helper function to check common constraint attributes."""
        self.assertEqual(constr.Sense, expected_sense)
        self.assertAlmostEqual(constr.RHS, expected_rhs)

        row = self.model.getRow(constr)
        self.assertEqual(row.size(), len(expected_lhs_terms_coeffs))

        actual_coeffs = {}
        for i in range(row.size()):
            actual_coeffs[row.getVar(i).VarName] = row.getCoeff(i)

        self.assertDictEqual(actual_coeffs, expected_lhs_terms_coeffs)

    def test_add_c_hourly_unit_ub(self):
        """Test add_c_hourly_unit_ub for wind units."""
        unit_type = "wind"
        units_to_test = self.wind_units
        timesteps_to_test = self.timesteps_hourly

        constrs = add_c_hourly_unit_ub(
            model=self.model,
            pdispatch=self.pdispatch,
            unit_type=unit_type,
            timesteps=timesteps_to_test,
            units=units_to_test,
            contracted_capacity_dict=self.contracted_capacity_dict,
        )
        self.model.update()

        self.assertEqual(
            len(constrs), len(units_to_test) * len(list(timesteps_to_test))
        )

        for unit in units_to_test:
            for t in timesteps_to_test:
                constr_name = f"hourly_{unit_type}_ub[{unit},{t}]"
                current_constr = self.model.getConstrByName(constr_name)
                self.assertIsNotNone(
                    current_constr, f"Constraint {constr_name} not found."
                )

                expected_rhs = self.contracted_capacity_dict[unit]
                expected_lhs_coeffs = {self.pdispatch[unit, t].VarName: 1.0}

                self._check_constr_details(
                    current_constr, gp.GRB.LESS_EQUAL, expected_rhs, expected_lhs_coeffs
                )

        # Test with empty units
        constrs_empty = add_c_hourly_unit_ub(
            model=self.model,
            pdispatch=self.pdispatch,
            unit_type="empty_test",
            timesteps=timesteps_to_test,
            units=[],
            contracted_capacity_dict=self.contracted_capacity_dict,
        )
        self.assertEqual(len(constrs_empty), 0)

    def test_add_c_link_unit_pu(self):
        """Test add_c_link_unit_pu for solar units."""
        unit_type = "solar"
        units_to_test = self.solar_units
        timesteps_to_test = self.timesteps_hourly

        constrs = add_c_link_unit_pu(
            model=self.model,
            pdispatch=self.pdispatch,
            u=self.u_status,
            unit_type=unit_type,
            timesteps=timesteps_to_test,
            units=units_to_test,
            contracted_capacity_dict=self.contracted_capacity_dict,
        )
        self.model.update()

        self.assertEqual(
            len(constrs), len(units_to_test) * len(list(timesteps_to_test))
        )

        for unit in units_to_test:
            for t in timesteps_to_test:
                constr_name = f"link_{unit_type}_pu[{unit},{t}]"
                current_constr = self.model.getConstrByName(constr_name)
                self.assertIsNotNone(
                    current_constr, f"Constraint {constr_name} not found."
                )

                # Constraint: pdispatch[unit, t] <= u[unit, t] * contracted_capacity_dict[unit]
                # Reformulated for Gurobi's getRow(): pdispatch[unit, t] - contracted_capacity_dict[unit] * u[unit, t] <= 0
                expected_rhs = 0.0
                expected_lhs_coeffs = {
                    self.pdispatch[unit, t].VarName: 1.0,
                    self.u_status[unit, t].VarName: -self.contracted_capacity_dict[
                        unit
                    ],
                }
                self._check_constr_details(
                    current_constr, gp.GRB.LESS_EQUAL, expected_rhs, expected_lhs_coeffs
                )

        # Test with empty units
        constrs_empty = add_c_link_unit_pu(
            model=self.model,
            pdispatch=self.pdispatch,
            u=self.u_status,
            unit_type="empty_test",
            timesteps=timesteps_to_test,
            units=[],
            contracted_capacity_dict=self.contracted_capacity_dict,
        )
        self.assertEqual(len(constrs_empty), 0)

    def test_add_c_hydro_limit_daily(self):
        """Test add_c_hydro_limit_daily."""
        # Test ValueError for invalid sim_horizon
        with self.assertRaisesRegex(
            ValueError, "simulation horizon must be divisible by 24"
        ):
            add_c_hydro_limit_daily(
                model=self.model,
                phydro=self.phydro,
                step_k=self.step_k_daily,
                sim_horizon=25,  # Invalid
                hydro_units=self.hydro_units,
                hydro_capacity=self.hydro_capacity_df_daily,
            )

        # Test with single day sim_horizon
        sim_horizon_test = self.sim_horizon_daily
        hydro_capacity_test_df = self.hydro_capacity_df_daily
        constrs = add_c_hydro_limit_daily(
            model=self.model,
            phydro=self.phydro,
            step_k=self.step_k_daily,
            sim_horizon=sim_horizon_test,
            hydro_units=self.hydro_units,
            hydro_capacity=hydro_capacity_test_df,
        )
        self.model.update()

        max_day = sim_horizon_test // 24
        self.assertEqual(len(constrs), len(self.hydro_units) * max_day)

        for day_offset in range(max_day):
            day_idx_in_df = self.step_k_daily + day_offset
            current_day_in_constr_name = (
                day_offset + 1
            )  # Constraint naming uses 1-based indexing for the day within the horizon
            for unit in self.hydro_units:
                constr_name = f"hydro_limit_daily[{unit},{current_day_in_constr_name}]"
                current_constr = self.model.getConstrByName(
                    constr_name
                )  # Direct get by name
                if (
                    current_constr is None
                ):  # Fallback if naming convention slight mismatch
                    current_constr = constrs.get(
                        (unit, current_day_in_constr_name)
                    )  # Check if key is tuple
                    if current_constr is None:
                        current_constr = constrs.get(
                            constr_name
                        )  # Check if key is string as generated

                self.assertIsNotNone(
                    current_constr, f"Constraint {constr_name} not found."
                )

                expected_rhs = hydro_capacity_test_df.loc[day_idx_in_df, unit]

                expected_lhs_coeffs = {}
                # Timesteps for this day: 1 + (current_day_in_constr_name - 1) * 24 to current_day_in_constr_name * 24
                start_t = 1 + (current_day_in_constr_name - 1) * 24
                end_t = current_day_in_constr_name * 24
                for t in range(start_t, end_t + 1):
                    expected_lhs_coeffs[self.phydro[unit, t].VarName] = 1.0

                self._check_constr_details(
                    current_constr, gp.GRB.LESS_EQUAL, expected_rhs, expected_lhs_coeffs
                )
                self.assertEqual(
                    len(expected_lhs_coeffs), 24, "Should sum over 24 hourly variables."
                )

        # Test with multiple days sim_horizon (e.g., 48 hours)
        sim_horizon_test_2days = self.sim_horizon_2days
        hydro_capacity_test_df_2days = self.hydro_capacity_df_2days
        constrs_2days = add_c_hydro_limit_daily(
            model=self.model,
            phydro=self.phydro,
            step_k=self.step_k_daily,
            sim_horizon=sim_horizon_test_2days,
            hydro_units=self.hydro_units,
            hydro_capacity=hydro_capacity_test_df_2days,
        )
        self.model.update()

        max_day_2days = sim_horizon_test_2days // 24
        self.assertEqual(len(constrs_2days), len(self.hydro_units) * max_day_2days)

        for day_offset in range(max_day_2days):
            day_idx_in_df = self.step_k_daily + day_offset
            current_day_in_constr_name = day_offset + 1
            for unit in self.hydro_units:
                constr_name = f"hydro_limit_daily[{unit},{current_day_in_constr_name}]"
                current_constr = self.model.getConstrByName(constr_name)
                self.assertIsNotNone(
                    current_constr, f"Constraint {constr_name} not found."
                )

                expected_rhs = hydro_capacity_test_df_2days.loc[day_idx_in_df, unit]
                expected_lhs_coeffs = {}
                start_t = 1 + (current_day_in_constr_name - 1) * 24
                end_t = current_day_in_constr_name * 24
                for t in range(start_t, end_t + 1):
                    expected_lhs_coeffs[self.phydro[unit, t].VarName] = 1.0

                self._check_constr_details(
                    current_constr, gp.GRB.LESS_EQUAL, expected_rhs, expected_lhs_coeffs
                )
                self.assertEqual(len(expected_lhs_coeffs), 24)

        # Test with empty hydro_units
        constrs_empty = add_c_hydro_limit_daily(
            model=self.model,
            phydro=self.phydro,
            step_k=self.step_k_daily,
            sim_horizon=sim_horizon_test,
            hydro_units=[],
            hydro_capacity=hydro_capacity_test_df,
        )
        self.assertEqual(len(constrs_empty), 0)

    def test_add_c_hydro_limit_daily_dict(self):
        """Test add_c_hydro_limit_daily_dict."""
        # Test ValueError for invalid sim_horizon
        with self.assertRaisesRegex(
            ValueError, "simulation horizon must be divisible by 24"
        ):
            add_c_hydro_limit_daily_dict(
                model=self.model,
                phydro=self.phydro,
                step_k=self.step_k_daily,
                sim_horizon=25,  # Invalid
                hydro_units=self.hydro_units,
                hydro_capacity_dict=self.hydro_capacity_dict_daily,
            )

        # Test with empty hydro_units
        constrs_empty = add_c_hydro_limit_daily_dict(
            model=self.model,
            phydro=self.phydro,
            step_k=self.step_k_daily,
            sim_horizon=self.sim_horizon_daily,
            hydro_units=[],
            hydro_capacity_dict=self.hydro_capacity_dict_daily,
        )
        self.assertEqual(len(constrs_empty), 0)

        # Test with single day sim_horizon
        sim_horizon_test = self.sim_horizon_daily
        hydro_cap_dict_test = self.hydro_capacity_dict_daily
        constrs = add_c_hydro_limit_daily_dict(
            model=self.model,
            phydro=self.phydro,
            step_k=self.step_k_daily,
            sim_horizon=sim_horizon_test,
            hydro_units=self.hydro_units,
            hydro_capacity_dict=hydro_cap_dict_test,
        )
        self.model.update()

        max_day = sim_horizon_test // 24
        self.assertEqual(len(constrs), len(self.hydro_units) * max_day)

        for day_offset in range(max_day):
            day_idx_in_dict = self.step_k_daily + day_offset
            current_day_in_constr_name = day_offset + 1
            for unit in self.hydro_units:
                constr_name = f"hydro_limit_daily[{unit},{current_day_in_constr_name}]"
                current_constr = self.model.getConstrByName(constr_name)
                self.assertIsNotNone(
                    current_constr, f"Constraint {constr_name} not found."
                )

                expected_rhs = hydro_cap_dict_test[(unit, day_idx_in_dict)]

                expected_lhs_coeffs = {}
                start_t = 1 + (current_day_in_constr_name - 1) * 24
                end_t = current_day_in_constr_name * 24
                for t in range(start_t, end_t + 1):
                    expected_lhs_coeffs[self.phydro[unit, t].VarName] = 1.0

                self._check_constr_details(
                    current_constr, gp.GRB.LESS_EQUAL, expected_rhs, expected_lhs_coeffs
                )
                self.assertEqual(len(expected_lhs_coeffs), 24)

        # Test with multiple days sim_horizon (e.g., 48 hours)
        sim_horizon_test_2days = self.sim_horizon_2days
        hydro_cap_dict_test_2days = self.hydro_capacity_dict_2days

        constrs_2days = add_c_hydro_limit_daily_dict(
            model=self.model,
            phydro=self.phydro,
            step_k=self.step_k_daily,
            sim_horizon=sim_horizon_test_2days,
            hydro_units=self.hydro_units,
            hydro_capacity_dict=hydro_cap_dict_test_2days,
        )
        self.model.update()

        max_day_2days = sim_horizon_test_2days // 24
        self.assertEqual(len(constrs_2days), len(self.hydro_units) * max_day_2days)

        for day_offset in range(max_day_2days):
            day_idx_in_dict = self.step_k_daily + day_offset
            current_day_in_constr_name = day_offset + 1
            for unit in self.hydro_units:
                constr_name = f"hydro_limit_daily[{unit},{current_day_in_constr_name}]"
                current_constr = self.model.getConstrByName(constr_name)
                self.assertIsNotNone(
                    current_constr, f"Constraint {constr_name} not found."
                )

                expected_rhs = hydro_cap_dict_test_2days[(unit, day_idx_in_dict)]
                expected_lhs_coeffs = {}
                start_t = 1 + (current_day_in_constr_name - 1) * 24
                end_t = current_day_in_constr_name * 24
                for t in range(start_t, end_t + 1):
                    expected_lhs_coeffs[self.phydro[unit, t].VarName] = 1.0

                self._check_constr_details(
                    current_constr, gp.GRB.LESS_EQUAL, expected_rhs, expected_lhs_coeffs
                )
                self.assertEqual(len(expected_lhs_coeffs), 24)

    def test_add_c_hydro_limit_weekly(self):
        """Test add_c_hydro_limit_weekly."""
        # Test ValueError for invalid sim_horizon
        with self.assertRaisesRegex(
            ValueError, "simulation horizon must be divisible by 168"
        ):
            add_c_hydro_limit_weekly(
                model=self.model,
                phydro=self.phydro,
                step_k=self.step_k_daily,  # step_k here is a week index for the data
                sim_horizon=167,  # Invalid
                hydro_units=self.hydro_units,
                hydro_capacity=self.hydro_capacity_weekly_df,
                hydro_capacity_min=self.hydro_capacity_min_weekly_df,
            )

        # Test with empty hydro_units
        constrs_empty = add_c_hydro_limit_weekly(
            model=self.model,
            phydro=self.phydro,
            step_k=self.step_k_daily,
            sim_horizon=self.sim_horizon_weekly,
            hydro_units=[],
            hydro_capacity=self.hydro_capacity_weekly_df,
            hydro_capacity_min=self.hydro_capacity_min_weekly_df,
        )
        self.assertEqual(len(constrs_empty), 0)

        # Test with single week sim_horizon
        sim_horizon_test = self.sim_horizon_weekly
        hydro_cap_df_test = self.hydro_capacity_weekly_df
        hydro_cap_min_df_test = self.hydro_capacity_min_weekly_df
        step_k_test = (
            self.step_k_daily
        )  # Assuming step_k refers to the starting week index for data lookup

        constrs = add_c_hydro_limit_weekly(
            model=self.model,
            phydro=self.phydro,
            step_k=step_k_test,
            sim_horizon=sim_horizon_test,
            hydro_units=self.hydro_units,
            hydro_capacity=hydro_cap_df_test,
            hydro_capacity_min=hydro_cap_min_df_test,
        )
        self.model.update()

        max_week = sim_horizon_test // 168
        # Expect 2 constraints (upper and lower bound) per unit per week
        self.assertEqual(len(constrs), len(self.hydro_units) * max_week * 2)

        for week_offset in range(max_week):
            week_idx_in_df = step_k_test + week_offset
            current_week_in_constr_name = week_offset + 1
            for unit in self.hydro_units:
                # Upper bound
                constr_name_ub = (
                    f"hydro_limit_weekly_ub[{unit},{current_week_in_constr_name}]"
                )
                current_constr_ub = self.model.getConstrByName(constr_name_ub)
                self.assertIsNotNone(
                    current_constr_ub, f"Constraint {constr_name_ub} not found."
                )

                expected_rhs_ub = hydro_cap_df_test.loc[week_idx_in_df, unit]
                expected_lhs_coeffs = {}
                start_t = 1 + (current_week_in_constr_name - 1) * 168
                end_t = current_week_in_constr_name * 168
                for t in range(start_t, end_t + 1):
                    expected_lhs_coeffs[self.phydro[unit, t].VarName] = 1.0

                self._check_constr_details(
                    current_constr_ub,
                    gp.GRB.LESS_EQUAL,
                    expected_rhs_ub,
                    expected_lhs_coeffs,
                )
                self.assertEqual(
                    len(expected_lhs_coeffs),
                    168,
                    "Should sum over 168 hourly variables for weekly UB.",
                )

                # Lower bound
                constr_name_lb = (
                    f"hydro_limit_weekly_lb[{unit},{current_week_in_constr_name}]"
                )
                current_constr_lb = self.model.getConstrByName(constr_name_lb)
                self.assertIsNotNone(
                    current_constr_lb, f"Constraint {constr_name_lb} not found."
                )

                expected_rhs_lb = hydro_cap_min_df_test.loc[week_idx_in_df, unit]
                # LHS coefficients are the same as for UB
                self._check_constr_details(
                    current_constr_lb,
                    gp.GRB.GREATER_EQUAL,
                    expected_rhs_lb,
                    expected_lhs_coeffs,
                )
                self.assertEqual(
                    len(expected_lhs_coeffs),
                    168,
                    "Should sum over 168 hourly variables for weekly LB.",
                )

        # Test with multiple weeks sim_horizon (e.g., 336 hours = 2 weeks)
        sim_horizon_test_2weeks = self.sim_horizon_2weeks
        hydro_cap_df_test_2w = self.hydro_capacity_2weeks_df
        hydro_cap_min_df_test_2w = self.hydro_capacity_min_2weeks_df

        constrs_2w = add_c_hydro_limit_weekly(
            model=self.model,
            phydro=self.phydro,
            step_k=step_k_test,
            sim_horizon=sim_horizon_test_2weeks,
            hydro_units=self.hydro_units,
            hydro_capacity=hydro_cap_df_test_2w,
            hydro_capacity_min=hydro_cap_min_df_test_2w,
        )
        self.model.update()

        max_week_2w = sim_horizon_test_2weeks // 168
        self.assertEqual(len(constrs_2w), len(self.hydro_units) * max_week_2w * 2)

        for week_offset in range(max_week_2w):
            week_idx_in_df = step_k_test + week_offset
            current_week_in_constr_name = week_offset + 1
            for unit in self.hydro_units:
                # Upper bound
                constr_name_ub = (
                    f"hydro_limit_weekly_ub[{unit},{current_week_in_constr_name}]"
                )
                current_constr_ub = self.model.getConstrByName(constr_name_ub)
                self.assertIsNotNone(
                    current_constr_ub, f"Constraint {constr_name_ub} not found."
                )

                expected_rhs_ub = hydro_cap_df_test_2w.loc[week_idx_in_df, unit]
                expected_lhs_coeffs = {}
                start_t = 1 + (current_week_in_constr_name - 1) * 168
                end_t = current_week_in_constr_name * 168
                for t in range(start_t, end_t + 1):
                    expected_lhs_coeffs[self.phydro[unit, t].VarName] = 1.0

                self._check_constr_details(
                    current_constr_ub,
                    gp.GRB.LESS_EQUAL,
                    expected_rhs_ub,
                    expected_lhs_coeffs,
                )
                self.assertEqual(len(expected_lhs_coeffs), 168)

                # Lower bound
                constr_name_lb = (
                    f"hydro_limit_weekly_lb[{unit},{current_week_in_constr_name}]"
                )
                current_constr_lb = self.model.getConstrByName(constr_name_lb)
                self.assertIsNotNone(
                    current_constr_lb, f"Constraint {constr_name_lb} not found."
                )

                expected_rhs_lb = hydro_cap_min_df_test_2w.loc[week_idx_in_df, unit]
                self._check_constr_details(
                    current_constr_lb,
                    gp.GRB.GREATER_EQUAL,
                    expected_rhs_lb,
                    expected_lhs_coeffs,
                )
                self.assertEqual(len(expected_lhs_coeffs), 168)


if __name__ == "__main__":
    unittest.main()
