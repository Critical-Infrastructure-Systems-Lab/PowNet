"""test_thermal_unit_constr.py"""

import unittest
import gurobipy as gp
import pandas as pd

from pownet.optim_model.constraints import thermal_unit_constr


class TestThermalUnitConstrs(unittest.TestCase):

    def setUp(self):
        """Set up common resources for each test method."""
        self.model = gp.Model("test_thermal_constraints")
        self.model.setParam("OutputFlag", 0)

        # Common test data
        self.thermal_units = ["G1", "G2"]
        self.sim_horizon_3 = 3
        self.timesteps = range(1, self.sim_horizon_3 + 1)

        # Define Gurobi variables
        self.u_vars = self.model.addVars(
            self.thermal_units, self.timesteps, vtype=gp.GRB.BINARY, name="u"
        )
        self.v_vars = self.model.addVars(
            self.thermal_units, self.timesteps, vtype=gp.GRB.BINARY, name="v"
        )
        self.w_vars = self.model.addVars(
            self.thermal_units, self.timesteps, vtype=gp.GRB.BINARY, name="w"
        )
        self.p_vars = self.model.addVars(
            self.thermal_units, self.timesteps, vtype=gp.GRB.CONTINUOUS, name="p"
        )
        self.pbar_vars = self.model.addVars(
            self.thermal_units, self.timesteps, vtype=gp.GRB.CONTINUOUS, name="pbar"
        )
        self.pthermal_vars = self.model.addVars(
            self.thermal_units, self.timesteps, vtype=gp.GRB.CONTINUOUS, name="pthermal"
        )
        self.spin_vars = self.model.addVars(
            self.thermal_units,
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            lb=0,
            name="spin",
        )

        # --- Test data for constraints ---
        # Initial conditions
        self.initial_u_data = {"G1": 0, "G2": 1}
        self.initial_min_off_data = {
            "G1": 5,  # initial_min_off > sim_horizon (5 > 3) => min_DT = 3
            "G2": 2,  # initial_min_off <= sim_horizon (2 <= 3) => min_DT = 2
        }

        self.thermal_min_capacity_data = {"G1": 50, "G2": 100}

        self.thermal_derated_capacity = pd.DataFrame(
            {"G1": [100, 100, 100], "G2": [200, 180, 160]},
        )
        self.thermal_derated_capacity.index += 1

        self.model.update()

    def test_add_c_link_uvw_init(self):
        # Add constraints for initial u values
        constrs = thermal_unit_constr.add_c_link_uvw_init(
            model=self.model,
            u=self.u_vars,
            v=self.v_vars,
            w=self.w_vars,
            thermal_units=self.thermal_units,
            initial_u=self.initial_u_data,
        )
        self.model.update()

        # Check the number of constraints added
        self.assertEqual(len(constrs), len(self.thermal_units))

        # Optional: Inspect a specific constraint
        # Constraint name is "link_uvw_init[G1]" or "link_uvw_init[G2]"
        g1_constr = self.model.getConstrByName("link_uvw_init[G1]")
        self.assertIsNotNone(g1_constr)
        self.assertEqual(g1_constr.Sense, gp.GRB.EQUAL)

        # Expression: u[G1,1] - initial_u[G1] == v[G1,1] - w[G1,1]
        # u[G1,1] - v[G1,1] + w[G1,1] == initial_u[G1]
        row = self.model.getRow(g1_constr)
        self.assertEqual(g1_constr.RHS, self.initial_u_data["G1"])

        # Check coefficients
        expected_coeffs_G1 = {
            self.u_vars["G1", 1].VarName: 1.0,
            self.v_vars["G1", 1].VarName: -1.0,
            self.w_vars["G1", 1].VarName: 1.0,
        }
        actual_coeffs_G1 = {}
        for i in range(row.size()):
            actual_coeffs_G1[row.getVar(i).VarName] = row.getCoeff(i)
        self.assertDictEqual(actual_coeffs_G1, expected_coeffs_G1)

        # Remove constraints
        self.model.remove(constrs)

    def test_add_c_link_uvw(self):
        constrs = thermal_unit_constr.add_c_link_uvw(
            model=self.model,
            u=self.u_vars,
            v=self.v_vars,
            w=self.w_vars,
            sim_horizon=self.sim_horizon_3,
            thermal_units=self.thermal_units,
        )
        self.model.update()

        # For t=2 and t=3
        expected_added_constrs = len(self.thermal_units) * (self.sim_horizon_3 - 1)
        self.assertEqual(self.model.NumConstrs, expected_added_constrs)
        self.assertEqual(len(constrs), expected_added_constrs)

        # Clean up: remove constraints
        self.model.remove(constrs)

    def test_add_c_link_pthermal(self):
        constrs = thermal_unit_constr.add_c_link_pthermal(
            model=self.model,
            pthermal=self.pthermal_vars,
            p=self.p_vars,
            u=self.u_vars,
            timesteps=self.timesteps,
            thermal_units=self.thermal_units,
            thermal_min_capacity=self.thermal_min_capacity_data,
        )
        self.model.update()

        expected_added_constrs = len(self.thermal_units) * self.sim_horizon_3
        self.assertEqual(self.model.NumConstrs, expected_added_constrs)
        self.assertEqual(len(constrs), expected_added_constrs)

        # Example: Inspect constraint for G2, t=2: "link_pthermal[G2,2]"
        # pthermal[G2,2] == p[G2,2] + thermal_min_capacity[G2] * u[G2,2]
        # pthermal[G2,2] - p[G2,2] - min_cap[G2]*u[G2,2] == 0
        constr_G2_t2 = self.model.getConstrByName("link_pthermal[G2,2]")
        self.assertIsNotNone(constr_G2_t2)
        self.assertEqual(constr_G2_t2.Sense, gp.GRB.EQUAL)
        self.assertEqual(constr_G2_t2.RHS, 0)

        row = self.model.getRow(constr_G2_t2)
        expected_coeffs = {
            self.pthermal_vars["G2", 2].VarName: 1.0,
            self.p_vars["G2", 2].VarName: -1.0,
            self.u_vars["G2", 2].VarName: -self.thermal_min_capacity_data["G2"],  # -100
        }
        actual_coeffs = {
            row.getVar(i).VarName: row.getCoeff(i) for i in range(row.size())
        }
        self.assertDictEqual(actual_coeffs, expected_coeffs)

        # Clean up: remove constraints
        self.model.remove(constrs)

    def test_add_c_link_spin(self):
        """Tests the add_c_link_spin constraint generation."""
        added_constrs = thermal_unit_constr.add_c_link_spin(
            self.model,
            self.p_vars,
            self.pbar_vars,
            self.spin_vars,
            self.timesteps,
            self.thermal_units,
        )
        self.model.update()

        expected_num_new_constrs = len(self.thermal_units) * len(self.timesteps)

        self.assertIsInstance(
            added_constrs, gp.tupledict, "Function should return a Gurobi tupledict."
        )
        self.assertEqual(
            len(added_constrs),
            expected_num_new_constrs,
            "Incorrect number of constraints in the returned tupledict.",
        )
        self.assertEqual(
            self.model.numConstrs,
            expected_num_new_constrs,
            "Model's total constraint count is incorrect after adding constraints.",
        )

        for unit in self.thermal_units:
            for t in self.timesteps:
                self.assertIn(
                    (unit, t),
                    added_constrs,
                    f"Constraint for ({unit},{t}) not found in returned tupledict.",
                )

                constr = added_constrs[unit, t]

                self.assertEqual(
                    constr.ConstrName,
                    f"link_spin[{unit},{t}]",
                    f"Incorrect constraint name for ({unit},{t}).",
                )
                self.assertEqual(
                    constr.getAttr(gp.GRB.Attr.Sense),
                    gp.GRB.EQUAL,
                    f"Constraint sense is not EQUAL for ({unit},{t}).",
                )
                self.assertEqual(
                    constr.getAttr(gp.GRB.Attr.RHS),
                    0.0,
                    f"Constraint RHS is not 0.0 for ({unit},{t}).",
                )

                expr = self.model.getRow(constr)

                self.assertEqual(
                    expr.size(),
                    3,
                    f"Constraint expression for ({unit},{t}) should involve 3 variables.",
                )

                # Store actual coefficients found for the expected variables
                # We'll map variable names to their coefficients in the expression
                actual_coeffs = {}
                for i in range(expr.size()):
                    var_in_expr = expr.getVar(i)
                    coeff_in_expr = expr.getCoeff(i)
                    actual_coeffs[var_in_expr.VarName] = coeff_in_expr

                # Define expected variable names for clarity
                expected_pbar_var_name = self.pbar_vars[unit, t].VarName
                expected_p_var_name = self.p_vars[unit, t].VarName
                expected_spin_var_name = self.spin_vars[unit, t].VarName

                # Check the coefficients of each variable in the normalized expression:
                # pbar[unit, t] - p[unit, t] - spin[unit, t] == 0
                self.assertEqual(
                    actual_coeffs.get(expected_pbar_var_name),
                    1.0,
                    f"Incorrect coefficient for {expected_pbar_var_name} in constraint for ({unit},{t}).",
                )
                self.assertEqual(
                    actual_coeffs.get(expected_p_var_name),
                    -1.0,
                    f"Incorrect coefficient for {expected_p_var_name} in constraint for ({unit},{t}).",
                )
                self.assertEqual(
                    actual_coeffs.get(expected_spin_var_name),
                    -1.0,
                    f"Incorrect coefficient for {expected_spin_var_name} in constraint for ({unit},{t}).",
                )

                # Ensure that the keys in actual_coeffs are exactly the ones we expect
                # (verifies that no other unexpected variables are in the constraint expression)
                expected_var_names_set = {
                    expected_pbar_var_name,
                    expected_p_var_name,
                    expected_spin_var_name,
                }
                self.assertEqual(
                    set(actual_coeffs.keys()),
                    expected_var_names_set,
                    f"Unexpected set of variables in constraint for ({unit},{t}).",
                )

        # Clean up: remove constraints
        self.model.remove(added_constrs)

    def test_add_c_link_ppbar(self):
        """Test the add_c_link_ppbar constraint function."""
        constrs = thermal_unit_constr.add_c_link_ppbar(
            model=self.model,
            p=self.p_vars,
            pbar=self.pbar_vars,
            timesteps=self.timesteps,
            thermal_units=self.thermal_units,
        )
        self.model.update()

        # Check the number of constraints added
        expected_num_constrs = len(self.thermal_units) * len(self.timesteps)
        self.assertEqual(len(constrs), expected_num_constrs)

        # Inspect a specific constraint (e.g., for G1 at timestep 1)
        # Constraint name is "link_ppbar[G1,1]"
        test_unit = self.thermal_units[0]
        test_t = list(self.timesteps)[0]
        constr_name = f"link_ppbar[{test_unit},{test_t}]"
        specific_constr = self.model.getConstrByName(constr_name)
        self.assertIsNotNone(specific_constr, f"Constraint {constr_name} not found.")

        # Constraint is pbar[unit, t] >= p[unit, t]
        # which is pbar[unit, t] - p[unit, t] >= 0
        self.assertEqual(specific_constr.Sense, gp.GRB.GREATER_EQUAL)
        self.assertEqual(specific_constr.RHS, 0.0)

        # Check coefficients
        row = self.model.getRow(specific_constr)
        expected_coeffs = {
            self.pbar_vars[test_unit, test_t].VarName: 1.0,
            self.p_vars[test_unit, test_t].VarName: -1.0,
        }
        actual_coeffs = {}
        for i in range(row.size()):
            actual_coeffs[row.getVar(i).VarName] = row.getCoeff(i)
        self.assertDictEqual(actual_coeffs, expected_coeffs)

        # Check another constraint to be sure (e.g., for G2 at timestep 2)
        if len(self.thermal_units) > 1 and len(list(self.timesteps)) > 1:
            test_unit_2 = self.thermal_units[1]
            test_t_2 = list(self.timesteps)[1]
            constr_name_2 = f"link_ppbar[{test_unit_2},{test_t_2}]"
            specific_constr_2 = self.model.getConstrByName(constr_name_2)
            self.assertIsNotNone(
                specific_constr_2, f"Constraint {constr_name_2} not found."
            )
            self.assertEqual(specific_constr_2.Sense, gp.GRB.GREATER_EQUAL)
            self.assertEqual(specific_constr_2.RHS, 0.0)

            row_2 = self.model.getRow(specific_constr_2)
            expected_coeffs_2 = {
                self.pbar_vars[test_unit_2, test_t_2].VarName: 1.0,
                self.p_vars[test_unit_2, test_t_2].VarName: -1.0,
            }
            actual_coeffs_2 = {}
            for i in range(row_2.size()):
                actual_coeffs_2[row_2.getVar(i).VarName] = row_2.getCoeff(i)
            self.assertDictEqual(actual_coeffs_2, expected_coeffs_2)

        # Remove constraints
        self.model.remove(constrs)

    def test_add_c_link_pu_lower(self):
        constrs = thermal_unit_constr.add_c_link_pu_lower(
            model=self.model,
            pthermal=self.pthermal_vars,
            u=self.u_vars,
            timesteps=self.timesteps,
            thermal_units=self.thermal_units,
            thermal_min_capacity=self.thermal_min_capacity_data,
        )
        self.model.update()
        expected_num_constrs = len(self.thermal_units) * len(self.timesteps)
        self.assertEqual(len(constrs), expected_num_constrs)

        # Inspect a specific constraint
        test_unit = self.thermal_units[0]
        test_t = self.timesteps[0]
        constr_name = f"pthermal_lb[{test_unit},{test_t}]"
        specific_constr = self.model.getConstrByName(constr_name)
        self.assertIsNotNone(specific_constr, f"Constraint {constr_name} not found.")

        # Check constant on the RHS
        self.assertEqual(specific_constr.RHS, 0.0)

        # Check the number of terms in the LHS
        row = self.model.getRow(specific_constr)
        self.assertEqual(row.size(), 2)

        # Check which variables are involved in the LHS
        actual_var_names = {row.getVar(i).VarName for i in range(row.size())}
        expected_var_names = {
            self.pthermal_vars[test_unit, test_t].VarName,
            self.u_vars[test_unit, test_t].VarName,
        }
        self.assertSetEqual(actual_var_names, expected_var_names)
        self.model.remove(constrs)

    def test_add_c_link_pu_upper(self):
        """Test the add_c_link_pu_upper constraint function."""
        step_k_test = 1

        constrs = thermal_unit_constr.add_c_link_pu_upper(
            model=self.model,
            pbar=self.pbar_vars,
            u=self.u_vars,
            timesteps=self.timesteps,
            step_k=step_k_test,
            thermal_units=self.thermal_units,
            thermal_min_capacity=self.thermal_min_capacity_data,
            thermal_derated_capacity=self.thermal_derated_capacity,
        )
        self.model.update()

        # Check the number of constraints added
        expected_num_constrs = len(self.thermal_units) * len(self.timesteps)
        self.assertEqual(len(constrs), expected_num_constrs)

        # Inspect a specific constraint (e.g., for G1 at timestep 1)
        test_unit = self.thermal_units[0]  # "G1"
        test_t = self.timesteps[0]  # 1

        # Constraint name is "pthermal_ub[G1,1]"
        constr_name = f"pthermal_ub[{test_unit},{test_t}]"
        specific_constr = self.model.getConstrByName(constr_name)
        self.assertIsNotNone(specific_constr, f"Constraint {constr_name} not found.")

        # Original constraint:
        # pbar[u,t] + min_cap[u]*u[u,t] <= derated_cap.loc[t+(k-1)*24, u]*u[u,t]
        # Rearranged:
        # pbar[u,t] + (min_cap[u] - derated_cap.loc[idx,u]) * u[u,t] <= 0
        self.assertEqual(specific_constr.RHS, 0.0)

        row = self.model.getRow(specific_constr)
        # Expecting 2 terms in the LHS: one for pbar, one for u
        self.assertEqual(row.size(), 2)

        # Check which variables are involved
        actual_var_names = {row.getVar(i).VarName for i in range(row.size())}
        expected_var_names = {
            self.pbar_vars[test_unit, test_t].VarName,
            self.u_vars[test_unit, test_t].VarName,
        }
        self.assertSetEqual(actual_var_names, expected_var_names)

        self.model.remove(constrs)

    def test_add_c_min_down_init(self):
        """Test the add_c_min_down_init constraint function."""

        constrs = thermal_unit_constr.add_c_min_down_init(
            model=self.model,
            u=self.u_vars,
            sim_horizon=self.sim_horizon_3,  # Assuming self.sim_horizon from setUp is desired (e.g., 3)
            thermal_units=self.thermal_units,
            initial_min_off=self.initial_min_off_data,
        )
        self.model.update()

        # Check the number of constraints added
        # The function returns a tupledict where keys are constraint names
        self.assertEqual(len(constrs), len(self.thermal_units))

        # --- Test Case for G1 ---
        # initial_min_off["G1"] = 5, sim_horizon = 3 => min_DT_G1 = min(5, 3) = 3
        # Constraint: u.sum(G1, range(1, 3+1)) == 0
        min_dt_g1 = min(self.initial_min_off_data["G1"], self.sim_horizon_3)
        self.assertEqual(min_dt_g1, 3)

        constr_g1_name = "minDownInit[G1]"
        constr_g1 = constrs.get(constr_g1_name)
        self.assertIsNotNone(constr_g1, f"Constraint {constr_g1_name} not found.")
        self.assertEqual(constr_g1.Sense, gp.GRB.EQUAL)
        self.assertEqual(constr_g1.RHS, 0.0)

        # The constraint should sum u[G1,1], u[G1,2], u[G1,3]
        row_g1 = self.model.getRow(constr_g1)
        self.assertEqual(row_g1.size(), min_dt_g1)

        actual_coeffs_g1 = {}
        for i in range(row_g1.size()):
            var = row_g1.getVar(i)
            actual_coeffs_g1[var.VarName] = row_g1.getCoeff(i)

        expected_coeffs_g1 = {}
        for t in range(1, min_dt_g1 + 1):
            expected_coeffs_g1[self.u_vars["G1", t].VarName] = 1.0
        self.assertDictEqual(actual_coeffs_g1, expected_coeffs_g1)

        # --- Test Case for G2 ---
        # initial_min_off["G2"] = 2, sim_horizon = 3 => min_DT_G2 = min(2, 3) = 2
        # Constraint: u.sum(G2, range(1, 2+1)) == 0
        min_dt_g2 = min(self.initial_min_off_data["G2"], self.sim_horizon_3)
        self.assertEqual(min_dt_g2, 2)

        constr_g2_name = "minDownInit[G2]"
        constr_g2 = constrs.get(constr_g2_name)
        self.assertIsNotNone(constr_g2, f"Constraint {constr_g2_name} not found.")
        self.assertEqual(constr_g2.Sense, gp.GRB.EQUAL)
        self.assertEqual(constr_g2.RHS, 0.0)

        row_g2 = self.model.getRow(constr_g2)
        self.assertEqual(row_g2.size(), min_dt_g2)

        actual_coeffs_g2 = {}
        for i in range(row_g2.size()):
            var = row_g2.getVar(i)
            actual_coeffs_g2[var.VarName] = row_g2.getCoeff(i)

        expected_coeffs_g2 = {}
        for t in range(1, min_dt_g2 + 1):
            expected_coeffs_g2[self.u_vars["G2", t].VarName] = 1.0
        self.assertDictEqual(actual_coeffs_g2, expected_coeffs_g2)

        # Clean up: remove constraints
        self.model.remove(constrs)

    def test_add_c_min_up_init(self):
        initial_min_on_long = {"G1": 5, "G2": 1}

        constrs = thermal_unit_constr.add_c_min_up_init(
            model=self.model,
            u=self.u_vars,
            sim_horizon=self.sim_horizon_3,
            thermal_units=self.thermal_units,
            initial_min_on=initial_min_on_long,
        )
        self.model.update()

        # Check the number of constraints added
        self.assertEqual(self.model.NumConstrs, len(self.thermal_units))

        # For G1, min_UT = min(5, 3) = 3. Constraint: u.sum(G1, 1..3) == 3
        constr_g1 = self.model.getConstrByName("minUpInit[G1]")
        self.assertIsNotNone(constr_g1)
        self.assertEqual(constr_g1.Sense, gp.GRB.EQUAL)
        self.assertEqual(constr_g1.RHS, 3)  # RHS should be capped min_UT
        row_g1 = self.model.getRow(constr_g1)

        # Check that u[G1,1], u[G1,2], u[G1,3] all have coeff 1
        for t_idx in range(1, self.sim_horizon_3 + 1):
            self.assertEqual(
                row_g1.getCoeff(row_g1.size() - self.sim_horizon_3 + t_idx - 1), 1.0
            )

        # For G2, min_UT = min(1, 3) = 1. Constraint: u.sum(G2, 1..1) == 1 => u[G2,1] == 1
        constr_g2 = self.model.getConstrByName("minUpInit[G2]")
        self.assertIsNotNone(constr_g2)
        self.assertEqual(constr_g2.Sense, gp.GRB.EQUAL)
        self.assertEqual(constr_g2.RHS, 1)
        row_g2 = self.model.getRow(constr_g2)
        self.assertEqual(row_g2.getVar(0).VarName, self.u_vars["G2", 1].VarName)
        self.assertEqual(row_g2.getCoeff(0), 1.0)
        self.assertEqual(row_g2.size(), 1)

        # Clean up: remove constraints
        self.model.remove(constrs)

    def test_add_c_min_down(self):
        """Test the add_c_min_down constraint function for t > 1."""

        # Define TD (minimum downtime) data for the test
        # G1: TD_g = 2. With sim_horizon = 3, constraints for t=2, t=3.
        # G2: TD_g = 4. With sim_horizon = 3, range(4, 3+1) is empty, so no constraints for G2.
        td_data = {"G1": 2, "G2": 4}

        constrs = thermal_unit_constr.add_c_min_down(
            model=self.model,
            u=self.u_vars,
            w=self.w_vars,
            sim_horizon=self.sim_horizon_3,
            thermal_units=self.thermal_units,
            TD=td_data,
        )
        self.model.update()

        # Calculate expected number of constraints
        expected_num_constrs = 0
        for unit in self.thermal_units:
            td_g = td_data.get(
                unit, float("inf")
            )  # Use a large default if unit not in td_data
            # The loop for t is range(td_g, self.sim_horizon + 1)
            if self.sim_horizon_3 >= td_g:
                expected_num_constrs += self.sim_horizon_3 - td_g + 1

        self.assertEqual(len(constrs), expected_num_constrs)
        self.assertEqual(expected_num_constrs, 2)  # Based on td_data and sim_horizon=3

        # --- Test Constraints for G1 ---
        # TD["G1"] = 2, sim_horizon = 3. Expect constraints for t=2 and t=3.
        td_g1 = td_data["G1"]

        # Case 1: G1, t = 2
        # LHS = w[G1, 2-2+1] + w[G1, 2] = w[G1,1] + w[G1,2]
        # Constraint: w[G1,1] + w[G1,2] <= 1 - u[G1,2]  =>  w[G1,1] + w[G1,2] + u[G1,2] <= 1
        t_g1_case1 = 2
        if t_g1_case1 >= td_g1:  # Ensure this constraint should exist
            constr_g1_t2_name = f"minDown[G1,{t_g1_case1}]"
            constr_g1_t2 = constrs.get(constr_g1_t2_name)
            self.assertIsNotNone(
                constr_g1_t2, f"Constraint {constr_g1_t2_name} not found."
            )

            self.assertEqual(constr_g1_t2.RHS, 1.0)
            self.assertIn(constr_g1_t2.Sense, [gp.GRB.LESS_EQUAL, gp.GRB.GREATER_EQUAL])

            row_g1_t2 = self.model.getRow(constr_g1_t2)
            # Expected variables: w[G1,1], w[G1,2], u[G1,2]
            self.assertEqual(row_g1_t2.size(), 3)

            actual_coeffs_g1_t2 = {}
            for i in range(row_g1_t2.size()):
                var = row_g1_t2.getVar(i)
                actual_coeffs_g1_t2[var.VarName] = row_g1_t2.getCoeff(i)

            expected_coeffs_g1_t2_le = {
                self.w_vars["G1", 1].VarName: 1.0,
                self.w_vars["G1", 2].VarName: 1.0,
                self.u_vars["G1", 2].VarName: 1.0,
            }

            if constr_g1_t2.Sense == gp.GRB.LESS_EQUAL:
                self.assertDictEqual(actual_coeffs_g1_t2, expected_coeffs_g1_t2_le)
            elif constr_g1_t2.Sense == gp.GRB.GREATER_EQUAL:  # Gurobi flipped signs
                expected_coeffs_g1_t2_ge = {
                    k: -v for k, v in expected_coeffs_g1_t2_le.items()
                }
                self.assertDictEqual(actual_coeffs_g1_t2, expected_coeffs_g1_t2_ge)
                self.assertEqual(
                    constr_g1_t2.RHS, -1.0
                )  # RHS would also flip if sense flips like this
            else:
                self.fail(f"Unexpected constraint sense: {constr_g1_t2.Sense}")

        # Case 2: G1, t = 3
        # LHS = w[G1, 3-2+1] + w[G1, 3] = w[G1,2] + w[G1,3]
        # Constraint: w[G1,2] + w[G1,3] <= 1 - u[G1,3]  =>  w[G1,2] + w[G1,3] + u[G1,3] <= 1
        t_g1_case2 = 3
        if t_g1_case2 >= td_g1:  # Ensure this constraint should exist
            constr_g1_t3_name = f"minDown[G1,{t_g1_case2}]"
            constr_g1_t3 = constrs.get(constr_g1_t3_name)
            self.assertIsNotNone(
                constr_g1_t3, f"Constraint {constr_g1_t3_name} not found."
            )

            self.assertEqual(constr_g1_t3.RHS, 1.0)  # Assuming default representation
            self.assertIn(constr_g1_t3.Sense, [gp.GRB.LESS_EQUAL, gp.GRB.GREATER_EQUAL])

            row_g1_t3 = self.model.getRow(constr_g1_t3)
            # Expected variables: w[G1,2], w[G1,3], u[G1,3]
            self.assertEqual(row_g1_t3.size(), 3)

            actual_coeffs_g1_t3 = {}
            for i in range(row_g1_t3.size()):
                var = row_g1_t3.getVar(i)
                actual_coeffs_g1_t3[var.VarName] = row_g1_t3.getCoeff(i)

            expected_coeffs_g1_t3_le = {
                self.w_vars["G1", 2].VarName: 1.0,
                self.w_vars["G1", 3].VarName: 1.0,
                self.u_vars["G1", 3].VarName: 1.0,
            }

            if constr_g1_t3.Sense == gp.GRB.LESS_EQUAL:
                self.assertDictEqual(actual_coeffs_g1_t3, expected_coeffs_g1_t3_le)
            elif constr_g1_t3.Sense == gp.GRB.GREATER_EQUAL:
                expected_coeffs_g1_t3_ge = {
                    k: -v for k, v in expected_coeffs_g1_t3_le.items()
                }
                self.assertDictEqual(actual_coeffs_g1_t3, expected_coeffs_g1_t3_ge)
                self.assertEqual(constr_g1_t3.RHS, -1.0)  # RHS would also flip
            else:
                self.fail(f"Unexpected constraint sense: {constr_g1_t3.Sense}")

        # --- Test Constraints for G2 ---
        # TD["G2"] = 4, sim_horizon = 3. No constraints expected.
        # This is implicitly checked by expected_num_constrs and len(constrs).
        # We can also explicitly check that no G2 constraint was added.
        td_g2 = td_data["G2"]
        for t_val in range(td_g2, self.sim_horizon_3 + 1):  # This loop shouldn't run
            constr_g2_name = f"minDown[G2,{t_val}]"
            self.assertIsNone(
                constrs.get(constr_g2_name),
                f"Constraint {constr_g2_name} should not exist for G2.",
            )

        # Clean up
        self.model.remove(constrs)

    def test_add_c_min_up(self):
        """Test the add_c_min_up constraint function for t > 1."""
        # Define TU (minimum uptime) data for the test
        # G1: TU_g = 2. With sim_horizon = 3, constraints for t=2, t=3.
        # G2: TU_g = 4. With sim_horizon = 3, range(4, 3+1) is empty, so no constraints for G2.
        tu_data = {"G1": 2, "G2": 4}

        constrs = thermal_unit_constr.add_c_min_up(
            model=self.model,
            u=self.u_vars,
            v=self.v_vars,  # Using startup variables
            sim_horizon=self.sim_horizon_3,
            thermal_units=self.thermal_units,
            TU=tu_data,
        )
        self.model.update()

        # Calculate expected number of constraints
        expected_num_constrs = 0
        for unit in self.thermal_units:
            tu_g = tu_data.get(
                unit, float("inf")
            )  # Use a large default if unit not in tu_data
            # The loop for t is range(tu_g, self.sim_horizon + 1)
            if self.sim_horizon_3 >= tu_g:
                expected_num_constrs += self.sim_horizon_3 - tu_g + 1

        self.assertEqual(len(constrs), expected_num_constrs)
        # Based on tu_data={"G1": 2, "G2": 4} and sim_horizon=3, expected_num_constrs is 2
        self.assertEqual(expected_num_constrs, 2)

        # --- Test Constraints for G1 ---
        # TU["G1"] = 2, sim_horizon = 3. Expect constraints for t=2 and t=3.
        tu_g1 = tu_data["G1"]

        # Case 1: G1, t = 2
        # LHS = v[G1, 2-2+1] + v[G1, 2] = v[G1,1] + v[G1,2]
        # Constraint: v[G1,1] + v[G1,2] <= u[G1,2]  =>  v[G1,1] + v[G1,2] - u[G1,2] <= 0
        t_g1_case1 = 2
        if t_g1_case1 >= tu_g1:  # Ensure this constraint should exist
            constr_g1_t2_name = f"minUp[G1,{t_g1_case1}]"  # Note: "minUp"
            constr_g1_t2 = constrs.get(constr_g1_t2_name)
            self.assertIsNotNone(
                constr_g1_t2, f"Constraint {constr_g1_t2_name} not found."
            )

            self.assertEqual(constr_g1_t2.RHS, 0.0)
            self.assertEqual(constr_g1_t2.Sense, gp.GRB.LESS_EQUAL)

            row_g1_t2 = self.model.getRow(constr_g1_t2)
            # Expected variables: v[G1,1], v[G1,2], u[G1,2]
            self.assertEqual(row_g1_t2.size(), 3)

            actual_coeffs_g1_t2 = {}
            for i in range(row_g1_t2.size()):
                var = row_g1_t2.getVar(i)
                actual_coeffs_g1_t2[var.VarName] = row_g1_t2.getCoeff(i)

            # If sense is LESS_EQUAL: v[G1,1] + v[G1,2] - u[G1,2] <= 0
            expected_coeffs_g1_t2_le = {
                self.v_vars["G1", 1].VarName: 1.0,
                self.v_vars["G1", 2].VarName: 1.0,
                self.u_vars["G1", 2].VarName: -1.0,  # u term is subtracted
            }

            self.assertDictEqual(actual_coeffs_g1_t2, expected_coeffs_g1_t2_le)

        # Case 2: G1, t = 3
        # LHS = v[G1, 3-2+1] + v[G1, 3] = v[G1,2] + v[G1,3]
        # Constraint: v[G1,2] + v[G1,3] <= u[G1,3]  =>  v[G1,2] + v[G1,3] - u[G1,3] <= 0
        t_g1_case2 = 3
        if t_g1_case2 >= tu_g1:  # Ensure this constraint should exist
            constr_g1_t3_name = f"minUp[G1,{t_g1_case2}]"
            constr_g1_t3 = constrs.get(constr_g1_t3_name)
            self.assertIsNotNone(
                constr_g1_t3, f"Constraint {constr_g1_t3_name} not found."
            )

            self.assertEqual(constr_g1_t3.RHS, 0.0)
            self.assertEqual(constr_g1_t3.Sense, gp.GRB.LESS_EQUAL)

            row_g1_t3 = self.model.getRow(constr_g1_t3)
            # Expected variables: v[G1,2], v[G1,3], u[G1,3]
            self.assertEqual(row_g1_t3.size(), 3)

            actual_coeffs_g1_t3 = {}
            for i in range(row_g1_t3.size()):
                var = row_g1_t3.getVar(i)
                actual_coeffs_g1_t3[var.VarName] = row_g1_t3.getCoeff(i)

            expected_coeffs_g1_t3_le = {
                self.v_vars["G1", 2].VarName: 1.0,
                self.v_vars["G1", 3].VarName: 1.0,
                self.u_vars["G1", 3].VarName: -1.0,
            }

            self.assertDictEqual(actual_coeffs_g1_t3, expected_coeffs_g1_t3_le)

        # --- Test Constraints for G2 ---
        # TU["G2"] = 4, sim_horizon = 3. No constraints expected.
        tu_g2 = tu_data["G2"]
        for t_val in range(tu_g2, self.sim_horizon_3 + 1):  # This loop shouldn't run
            constr_g2_name = f"minUp[G2,{t_val}]"  # Note: "minUp"
            self.assertIsNone(
                constrs.get(constr_g2_name),
                f"Constraint {constr_g2_name} should not exist for G2.",
            )

        # Clean up
        self.model.remove(constrs)

    def test_add_c_peak_down_bound(self):
        """Test the add_c_peak_down_bound constraint function."""

        # Test data for SD, SU, TU
        sd_data = {"G1": 70, "G2": 130}  # Shutdown capability (P_sd)
        su_data = {"G1": 50, "G2": 100}  # Startup capability (P_su)
        tu_data = {
            "G1": 1,
            "G2": 2,
        }  # Minimum Uptime: G1 will get constraints, G2 will not.

        # Assuming from setUp:
        step_k_data = 1

        constrs = thermal_unit_constr.add_c_peak_down_bound(
            model=self.model,
            p=self.p_vars,
            u=self.u_vars,
            v=self.v_vars,
            w=self.w_vars,
            sim_horizon=self.sim_horizon_3,
            step_k=step_k_data,
            thermal_units=self.thermal_units,
            thermal_min_capacity=self.thermal_min_capacity_data,
            thermal_derated_capacity=self.thermal_derated_capacity,
            SD=sd_data,
            SU=su_data,
            TU=tu_data,
        )
        self.model.update()

        # Calculate expected number of constraints
        # G1: TU=1. sim_horizon=3.
        #   - t=1 constraint (GentilePeakDown_t1) because sim_horizon >= 2. (1 constraint)
        #   - Intermediate loop for t in range(2, sim_horizon=3) => t=2. (1 constraint)
        # Total for G1 = 2.
        # G2: TU=2. No constraints.
        # Total expected = 2.
        expected_num_constrs = 0
        if tu_data.get("G1") == 1:
            if self.sim_horizon_3 >= 2:  # For t=1 constraint
                expected_num_constrs += 1
            if self.sim_horizon_3 > 2:  # For intermediate loop range(2, sim_horizon)
                expected_num_constrs += (
                    self.sim_horizon_3 - 2
                )  # t from 2 to sim_horizon-1

        self.assertEqual(len(constrs), expected_num_constrs)
        if (
            self.sim_horizon_3 == 3 and tu_data.get("G1") == 1
        ):  # Specific to current setup
            self.assertEqual(expected_num_constrs, 2)

        # --- Test constraints for G1 (where TU=1) ---
        unit_g1 = "G1"
        if tu_data.get(unit_g1) == 1:
            p_underline_g1 = self.thermal_min_capacity_data[unit_g1]

            # Case 1: t = 1 constraint (GentileEq_t1)
            if self.sim_horizon_3 >= 2:
                t1 = 1
                constr_g1_t1_key = (unit_g1, t1, "GentilePeakDown_t1")
                constr_g1_t1 = constrs.get(constr_g1_t1_key)
                self.assertIsNotNone(
                    constr_g1_t1, f"Constraint {constr_g1_t1_key} not found."
                )

                # Eq: p1 <= (Pbar1 - Punderline)u1 - (Pbar1 - SD)w2
                # -> p1 - (Pbar1 - Punderline)u1 + (Pbar1 - SD)w2 <= 0
                p_bar_t1_g1 = self.thermal_derated_capacity.loc[
                    t1 + (step_k_data - 1) * 24, unit_g1
                ]

                expected_rhs_t1 = 0.0
                expected_p1_coeff_le = 1.0
                expected_u1_coeff_le = p_underline_g1 - p_bar_t1_g1
                expected_w2_coeff_le = p_bar_t1_g1 - sd_data[unit_g1]

                self.assertIn(
                    constr_g1_t1.Sense, [gp.GRB.LESS_EQUAL, gp.GRB.GREATER_EQUAL]
                )
                self.assertAlmostEqual(constr_g1_t1.RHS, expected_rhs_t1)

                row_g1_t1 = self.model.getRow(constr_g1_t1)

                expected_coeffs_g1_t1_map = {}
                num_expected_terms = 0
                if abs(expected_p1_coeff_le) > 1e-9:
                    expected_coeffs_g1_t1_map[self.p_vars[unit_g1, t1].VarName] = (
                        expected_p1_coeff_le
                    )
                    num_expected_terms += 1
                if abs(expected_u1_coeff_le) > 1e-9:
                    expected_coeffs_g1_t1_map[self.u_vars[unit_g1, t1].VarName] = (
                        expected_u1_coeff_le
                    )
                    num_expected_terms += 1
                if abs(expected_w2_coeff_le) > 1e-9:
                    expected_coeffs_g1_t1_map[self.w_vars[unit_g1, t1 + 1].VarName] = (
                        expected_w2_coeff_le
                    )
                    num_expected_terms += 1

                self.assertEqual(row_g1_t1.size(), num_expected_terms)

                actual_coeffs_g1_t1 = {
                    row_g1_t1.getVar(i).VarName: row_g1_t1.getCoeff(i)
                    for i in range(row_g1_t1.size())
                }

                if constr_g1_t1.Sense == gp.GRB.LESS_EQUAL:
                    self.assertDictEqual(actual_coeffs_g1_t1, expected_coeffs_g1_t1_map)
                elif constr_g1_t1.Sense == gp.GRB.GREATER_EQUAL:
                    self.assertDictEqual(
                        actual_coeffs_g1_t1,
                        {k: -v for k, v in expected_coeffs_g1_t1_map.items()},
                    )
                else:
                    self.fail(f"Unexpected sense for {constr_g1_t1_key}")

            # Case 2: Intermediate t constraints (e.g., t=2 if sim_horizon=3)
            # Loop for t in range(2, sim_horizon)
            for t_intermediate in range(2, self.sim_horizon_3):
                constr_g1_intermediate_key = (
                    unit_g1,
                    t_intermediate,
                    "GentilePeakDown_intermediate",
                )
                constr_g1_intermediate = constrs.get(constr_g1_intermediate_key)
                self.assertIsNotNone(
                    constr_g1_intermediate,
                    f"Constraint {constr_g1_intermediate_key} not found.",
                )

                # Eq: pt <= (Pbart - Pu)ut - (Pbart - SD)w(t+1) - max(0, SD-SU)vt
                # -> pt - (Pbart - Pu)ut + (Pbart - SD)w(t+1) + max(0,SD-SU)vt <= 0
                p_bar_ti_g1 = self.thermal_derated_capacity.loc[
                    t_intermediate + (step_k_data - 1) * 24, unit_g1
                ]
                max_sd_su_term = max(
                    0, sd_data[unit_g1] - su_data[unit_g1]
                )  # For G1: max(0, 70-50)=20

                expected_rhs_ti = 0.0
                expected_pt_coeff_le = 1.0
                expected_ut_coeff_le = p_underline_g1 - p_bar_ti_g1
                expected_wtplus1_coeff_le = p_bar_ti_g1 - sd_data[unit_g1]
                expected_vt_coeff_le = max_sd_su_term

                self.assertIn(
                    constr_g1_intermediate.Sense,
                    [gp.GRB.LESS_EQUAL, gp.GRB.GREATER_EQUAL],
                )
                self.assertAlmostEqual(constr_g1_intermediate.RHS, expected_rhs_ti)

                row_g1_ti = self.model.getRow(constr_g1_intermediate)

                expected_coeffs_g1_ti_map = {}
                num_expected_terms_ti = 0
                if abs(expected_pt_coeff_le) > 1e-9:
                    expected_coeffs_g1_ti_map[
                        self.p_vars[unit_g1, t_intermediate].VarName
                    ] = expected_pt_coeff_le
                    num_expected_terms_ti += 1
                if abs(expected_ut_coeff_le) > 1e-9:
                    expected_coeffs_g1_ti_map[
                        self.u_vars[unit_g1, t_intermediate].VarName
                    ] = expected_ut_coeff_le
                    num_expected_terms_ti += 1
                if abs(expected_wtplus1_coeff_le) > 1e-9:
                    expected_coeffs_g1_ti_map[
                        self.w_vars[unit_g1, t_intermediate + 1].VarName
                    ] = expected_wtplus1_coeff_le
                    num_expected_terms_ti += 1
                if abs(expected_vt_coeff_le) > 1e-9:  # This term can be zero
                    expected_coeffs_g1_ti_map[
                        self.v_vars[unit_g1, t_intermediate].VarName
                    ] = expected_vt_coeff_le
                    num_expected_terms_ti += 1

                self.assertEqual(row_g1_ti.size(), num_expected_terms_ti)

                actual_coeffs_g1_ti = {
                    row_g1_ti.getVar(i).VarName: row_g1_ti.getCoeff(i)
                    for i in range(row_g1_ti.size())
                }

                if constr_g1_intermediate.Sense == gp.GRB.LESS_EQUAL:
                    self.assertDictEqual(actual_coeffs_g1_ti, expected_coeffs_g1_ti_map)
                elif constr_g1_intermediate.Sense == gp.GRB.GREATER_EQUAL:
                    self.assertDictEqual(
                        actual_coeffs_g1_ti,
                        {k: -v for k, v in expected_coeffs_g1_ti_map.items()},
                    )
                else:
                    self.fail(f"Unexpected sense for {constr_g1_intermediate_key}")

        # --- Verify no constraints for G2 (where TU=2) ---
        unit_g2 = "G2"
        if tu_data.get(unit_g2) != 1:
            # Check that no constraints for G2 were added to the returned tupledict
            g2_constr_keys = [key for key in constrs if key[0] == unit_g2]
            self.assertEqual(
                len(g2_constr_keys), 0, f"Constraints found for {unit_g2} when TU != 1"
            )

        # Clean up
        self.model.remove(constrs)

    def test_add_c_peak_up_bound(self):
        """Test the add_c_peak_up_bound constraint function."""

        # Test data for SD, SU, TU
        sd_data = {"G1": 50, "G2": 100}  # Shutdown capability (P_sd)
        su_data = {"G1": 70, "G2": 130}  # Startup capability (P_su)
        tu_data = {
            "G1": 1,
            "G2": 2,
        }  # Minimum Uptime: G1 will get constraints, G2 will not.

        step_k_data = 1

        constrs = thermal_unit_constr.add_c_peak_up_bound(
            model=self.model,
            p=self.p_vars,
            u=self.u_vars,
            v=self.v_vars,
            w=self.w_vars,
            sim_horizon=self.sim_horizon_3,
            step_k=step_k_data,
            thermal_units=self.thermal_units,
            thermal_min_capacity=self.thermal_min_capacity_data,
            thermal_derated_capacity=self.thermal_derated_capacity,
            SD=sd_data,
            SU=su_data,
            TU=tu_data,
        )
        self.model.update()

        # Calculate expected number of constraints
        # G1: TU=1. sim_horizon=3.
        #   - Intermediate loop for t in range(2, sim_horizon=3) => t=2. (1 constraint - GentileEq5)
        #   - Final t=T constraint (sim_horizon=3). (1 constraint - GentileEq3)
        # Total for G1 = 2.
        # G2: TU=2. No constraints.
        # Total expected = 2.
        expected_num_constrs = 0
        if tu_data.get("G1") == 1:
            if self.sim_horizon_3 > 1:  # Intermediate loop range(2, sim_horizon)
                expected_num_constrs += (
                    self.sim_horizon_3 - 2 + 1
                )  # t from 2 to sim_horizon-1
            if self.sim_horizon_3 >= 1:  # for final t=T constraint
                expected_num_constrs += 1

        # Correction for expected_num_constrs logic:
        expected_num_constrs_calc = 0
        for unit_g_calc in self.thermal_units:
            if tu_data.get(unit_g_calc) == 1:
                # Intermediate constraints
                if (
                    self.sim_horizon_3 > 2
                ):  # range(2, sim_horizon) means at least sim_horizon=3
                    expected_num_constrs_calc += (
                        self.sim_horizon_3 - 1 - 2 + 1
                    )  # t from 2 to sim_horizon-1
                # Final T constraint
                if self.sim_horizon_3 >= 1:
                    expected_num_constrs_calc += 1

        self.assertEqual(len(constrs), expected_num_constrs_calc)
        if (
            self.sim_horizon_3 == 3
            and tu_data.get("G1") == 1
            and tu_data.get("G2") != 1
        ):  # Specific to current setup
            self.assertEqual(
                expected_num_constrs_calc, 2
            )  # (t=2 intermediate) + (t=3 final)

        # --- Test constraints for G1 (where TU=1) ---
        unit_g1 = "G1"
        if tu_data.get(unit_g1) == 1:
            p_underline_g1 = self.thermal_min_capacity_data[unit_g1]

            # Case 1: Intermediate t constraints (GentileEq5)
            # Loop for t in range(2, sim_horizon)
            for t_intermediate in range(2, self.sim_horizon_3):
                constr_g1_intermediate_key = (
                    unit_g1,
                    t_intermediate,
                    "GentilePeakUp_intermediate",
                )
                constr_g1_intermediate = constrs.get(constr_g1_intermediate_key)
                self.assertIsNotNone(
                    constr_g1_intermediate,
                    f"Constraint {constr_g1_intermediate_key} not found.",
                )

                # Eq5: pt <= (Pbart - Pu)ut - (Pbart - SU)vt - max(0, SU-SD)w(t+1)
                # -> pt - (Pbart - Pu)ut + (Pbart - SU)vt + max(0,SU-SD)w(t+1) <= 0
                p_bar_ti_g1 = self.thermal_derated_capacity.loc[
                    t_intermediate + (step_k_data - 1) * 24, unit_g1
                ]
                max_su_sd_term = max(
                    0, su_data[unit_g1] - sd_data[unit_g1]
                )  # For G1: max(0, 70-50)=20

                expected_rhs_ti = 0.0
                expected_pt_coeff_le = 1.0
                expected_ut_coeff_le = p_underline_g1 - p_bar_ti_g1
                expected_vt_coeff_le = p_bar_ti_g1 - su_data[unit_g1]
                expected_wtplus1_coeff_le = max_su_sd_term

                self.assertIn(
                    constr_g1_intermediate.Sense,
                    [gp.GRB.LESS_EQUAL, gp.GRB.GREATER_EQUAL],
                )
                self.assertAlmostEqual(constr_g1_intermediate.RHS, expected_rhs_ti)

                row_g1_ti = self.model.getRow(constr_g1_intermediate)
                expected_coeffs_g1_ti_map = {}
                num_expected_terms_ti = 0

                if abs(expected_pt_coeff_le) > 1e-9:
                    expected_coeffs_g1_ti_map[
                        self.p_vars[unit_g1, t_intermediate].VarName
                    ] = expected_pt_coeff_le
                    num_expected_terms_ti += 1
                if abs(expected_ut_coeff_le) > 1e-9:
                    expected_coeffs_g1_ti_map[
                        self.u_vars[unit_g1, t_intermediate].VarName
                    ] = expected_ut_coeff_le
                    num_expected_terms_ti += 1
                if abs(expected_vt_coeff_le) > 1e-9:
                    expected_coeffs_g1_ti_map[
                        self.v_vars[unit_g1, t_intermediate].VarName
                    ] = expected_vt_coeff_le
                    num_expected_terms_ti += 1
                if abs(expected_wtplus1_coeff_le) > 1e-9:  # This term can be zero
                    expected_coeffs_g1_ti_map[
                        self.w_vars[unit_g1, t_intermediate + 1].VarName
                    ] = expected_wtplus1_coeff_le
                    num_expected_terms_ti += 1

                self.assertEqual(row_g1_ti.size(), num_expected_terms_ti)
                actual_coeffs_g1_ti = {
                    row_g1_ti.getVar(i).VarName: row_g1_ti.getCoeff(i)
                    for i in range(row_g1_ti.size())
                }

                if constr_g1_intermediate.Sense == gp.GRB.LESS_EQUAL:
                    self.assertDictEqual(actual_coeffs_g1_ti, expected_coeffs_g1_ti_map)
                elif constr_g1_intermediate.Sense == gp.GRB.GREATER_EQUAL:
                    self.assertDictEqual(
                        actual_coeffs_g1_ti,
                        {k: -v for k, v in expected_coeffs_g1_ti_map.items()},
                    )
                else:
                    self.fail(f"Unexpected sense for {constr_g1_intermediate_key}")

            # Case 2: Final t = T (sim_horizon) constraint (GentileEq3)
            if self.sim_horizon_3 >= 1:
                t_final = self.sim_horizon_3
                constr_g1_finalt_key = (unit_g1, t_final, "GentilePeakUp_finalT")
                constr_g1_finalt = constrs.get(constr_g1_finalt_key)
                self.assertIsNotNone(
                    constr_g1_finalt, f"Constraint {constr_g1_finalt_key} not found."
                )

                # Eq3: pT <= (PbarT - Pu)uT - (PbarT - SU)vT
                # -> pT - (PbarT - Pu)uT + (PbarT - SU)vT <= 0
                p_bar_tf_g1 = self.thermal_derated_capacity.loc[
                    t_final + (step_k_data - 1) * 24, unit_g1
                ]

                expected_rhs_tf = 0.0
                expected_ptf_coeff_le = 1.0
                expected_utf_coeff_le = p_underline_g1 - p_bar_tf_g1
                expected_vtf_coeff_le = p_bar_tf_g1 - su_data[unit_g1]

                self.assertIn(
                    constr_g1_finalt.Sense, [gp.GRB.LESS_EQUAL, gp.GRB.GREATER_EQUAL]
                )
                self.assertAlmostEqual(constr_g1_finalt.RHS, expected_rhs_tf)

                row_g1_tf = self.model.getRow(constr_g1_finalt)
                expected_coeffs_g1_tf_map = {}
                num_expected_terms_tf = 0

                if abs(expected_ptf_coeff_le) > 1e-9:
                    expected_coeffs_g1_tf_map[self.p_vars[unit_g1, t_final].VarName] = (
                        expected_ptf_coeff_le
                    )
                    num_expected_terms_tf += 1
                if abs(expected_utf_coeff_le) > 1e-9:
                    expected_coeffs_g1_tf_map[self.u_vars[unit_g1, t_final].VarName] = (
                        expected_utf_coeff_le
                    )
                    num_expected_terms_tf += 1
                if abs(expected_vtf_coeff_le) > 1e-9:
                    expected_coeffs_g1_tf_map[self.v_vars[unit_g1, t_final].VarName] = (
                        expected_vtf_coeff_le
                    )
                    num_expected_terms_tf += 1

                self.assertEqual(row_g1_tf.size(), num_expected_terms_tf)
                actual_coeffs_g1_tf = {
                    row_g1_tf.getVar(i).VarName: row_g1_tf.getCoeff(i)
                    for i in range(row_g1_tf.size())
                }

                if constr_g1_finalt.Sense == gp.GRB.LESS_EQUAL:
                    self.assertDictEqual(actual_coeffs_g1_tf, expected_coeffs_g1_tf_map)
                elif constr_g1_finalt.Sense == gp.GRB.GREATER_EQUAL:
                    self.assertDictEqual(
                        actual_coeffs_g1_tf,
                        {k: -v for k, v in expected_coeffs_g1_tf_map.items()},
                    )
                else:
                    self.fail(f"Unexpected sense for {constr_g1_finalt_key}")

        # --- Verify no constraints for G2 (where TU=2) ---
        unit_g2 = "G2"
        if tu_data.get(unit_g2) != 1:
            g2_constr_keys = [key for key in constrs if key[0] == unit_g2]
            self.assertEqual(
                len(g2_constr_keys), 0, f"Constraints found for {unit_g2} when TU != 1"
            )

        # Clean up
        if constrs:
            self.model.remove(constrs)
            self.model.update()

    def test_add_c_ramp_down_init(self):
        """Test the add_c_ramp_down_init constraint function."""
        # Define local test data
        initial_p_data = {"G1": 60, "G2": 110}  # Initial power above min capacity (t=0)
        initial_u_data = {"G1": 1, "G2": 0}  # Initial status (t=0), G1 is ON, G2 is OFF
        rd_data = {"G1": 20, "G2": 30}  # Ramp-down rate
        # Adjusted SD_data for G1 to ensure w_coeff is non-zero
        sd_data = {
            "G1": 60,
            "G2": 120,
        }  # Shutdown capability (max power output when shutting down)
        # or P_min + SD_ramp if SD_ramp is the shutdown ramp over 1hr

        constrs = thermal_unit_constr.add_c_ramp_down_init(
            model=self.model,
            p=self.p_vars,
            w=self.w_vars,
            thermal_units=self.thermal_units,
            initial_p=initial_p_data,
            initial_u=initial_u_data,
            thermal_min_capacity=self.thermal_min_capacity_data,
            RD=rd_data,
            SD=sd_data,
        )
        self.model.update()

        # Check the number of constraints added
        self.assertEqual(len(constrs), len(self.thermal_units))

        # --- Test Constraint for G1 ---
        unit_g1 = "G1"
        # Constraint: initial_p[G1] - p[G1,1] <= (SD[G1] - min_cap[G1] - RD[G1]) * w[G1,1] + RD[G1] * initial_u[G1]
        # Rearranged for Gurobi (variables on LHS, constants on RHS, for sense <=):
        # -p[G1,1] - (SD[G1] - min_cap[G1] - RD[G1]) * w[G1,1] <= RD[G1]*initial_u[G1] - initial_p[G1]
        # which is:
        # -p[G1,1] + (RD[G1] + min_cap[G1] - SD[G1]) * w[G1,1] <= RD[G1]*initial_u[G1] - initial_p[G1]

        constr_g1 = self.model.getConstrByName(f"rampDownInit[{unit_g1}]")
        self.assertIsNotNone(
            constr_g1, f"Constraint for {unit_g1} not found in returned tupledict."
        )

        # Calculate expected coefficients and RHS for G1
        # Coeff for p[G1,1] is -1.0
        # Coeff for w[G1,1] is (RD[G1] + min_cap[G1] - SD[G1])
        # RHS_val is (RD[G1] * initial_u[G1] - initial_p[G1])

        expected_p_coeff_g1_le = -1.0
        expected_w_coeff_g1_le = (
            rd_data[unit_g1]
            + self.thermal_min_capacity_data[unit_g1]
            - sd_data[unit_g1]
        )
        # For G1: 20 + 50 - 60 = 10
        expected_rhs_g1 = (
            rd_data[unit_g1] * initial_u_data[unit_g1] - initial_p_data[unit_g1]
        )
        # For G1: 20 * 1 - 60 = -40

        self.assertIn(constr_g1.Sense, [gp.GRB.LESS_EQUAL, gp.GRB.GREATER_EQUAL])

        row_g1 = self.model.getRow(constr_g1)

        # Determine expected number of terms (if a coeff is 0, Gurobi might omit it)
        expected_terms_g1 = 0
        if abs(expected_p_coeff_g1_le) > 1e-9:
            expected_terms_g1 += 1
        if abs(expected_w_coeff_g1_le) > 1e-9:
            expected_terms_g1 += 1
        self.assertEqual(row_g1.size(), expected_terms_g1)

        actual_coeffs_g1 = {}
        if row_g1.size() > 0:
            for i in range(row_g1.size()):
                var = row_g1.getVar(i)
                actual_coeffs_g1[var.VarName] = row_g1.getCoeff(i)

        expected_coeffs_g1_le_map = {}
        if abs(expected_p_coeff_g1_le) > 1e-9:
            expected_coeffs_g1_le_map[self.p_vars[unit_g1, 1].VarName] = (
                expected_p_coeff_g1_le
            )
        if abs(expected_w_coeff_g1_le) > 1e-9:
            expected_coeffs_g1_le_map[self.w_vars[unit_g1, 1].VarName] = (
                expected_w_coeff_g1_le
            )

        if constr_g1.Sense == gp.GRB.LESS_EQUAL:
            self.assertAlmostEqual(constr_g1.RHS, expected_rhs_g1)
            self.assertDictEqual(actual_coeffs_g1, expected_coeffs_g1_le_map)
        elif constr_g1.Sense == gp.GRB.GREATER_EQUAL:  # Gurobi flipped everything
            self.assertAlmostEqual(constr_g1.RHS, -expected_rhs_g1)
            expected_coeffs_g1_ge_map = {
                k: -v for k, v in expected_coeffs_g1_le_map.items()
            }
            self.assertDictEqual(actual_coeffs_g1, expected_coeffs_g1_ge_map)
        else:
            self.fail(f"Unexpected constraint sense for {unit_g1}: {constr_g1.Sense}")

        # --- Test Constraint for G2 ---
        unit_g2 = "G2"
        constr_g2 = self.model.getConstrByName(f"rampDownInit[{unit_g2}]")
        self.assertIsNotNone(constr_g2, f"Constraint for {unit_g2} not found.")

        expected_p_coeff_g2_le = -1.0
        expected_w_coeff_g2_le = (
            rd_data[unit_g2]
            + self.thermal_min_capacity_data[unit_g2]
            - sd_data[unit_g2]
        )
        # For G2: 30 + 100 - 120 = 10
        expected_rhs_g2 = (
            rd_data[unit_g2] * initial_u_data[unit_g2] - initial_p_data[unit_g2]
        )
        # For G2: 30 * 0 - 110 = -110

        self.assertIn(constr_g2.Sense, [gp.GRB.LESS_EQUAL, gp.GRB.GREATER_EQUAL])
        row_g2 = self.model.getRow(constr_g2)

        expected_terms_g2 = 0
        if abs(expected_p_coeff_g2_le) > 1e-9:
            expected_terms_g2 += 1
        if abs(expected_w_coeff_g2_le) > 1e-9:
            expected_terms_g2 += 1
        self.assertEqual(row_g2.size(), expected_terms_g2)

        actual_coeffs_g2 = {}
        if row_g2.size() > 0:
            for i in range(row_g2.size()):
                var = row_g2.getVar(i)
                actual_coeffs_g2[var.VarName] = row_g2.getCoeff(i)

        expected_coeffs_g2_le_map = {}
        if abs(expected_p_coeff_g2_le) > 1e-9:
            expected_coeffs_g2_le_map[self.p_vars[unit_g2, 1].VarName] = (
                expected_p_coeff_g2_le
            )
        if abs(expected_w_coeff_g2_le) > 1e-9:
            expected_coeffs_g2_le_map[self.w_vars[unit_g2, 1].VarName] = (
                expected_w_coeff_g2_le
            )

        if constr_g2.Sense == gp.GRB.LESS_EQUAL:
            self.assertAlmostEqual(constr_g2.RHS, expected_rhs_g2)
            self.assertDictEqual(actual_coeffs_g2, expected_coeffs_g2_le_map)
        elif constr_g2.Sense == gp.GRB.GREATER_EQUAL:
            self.assertAlmostEqual(constr_g2.RHS, -expected_rhs_g2)
            expected_coeffs_g2_ge_map = {
                k: -v for k, v in expected_coeffs_g2_le_map.items()
            }
            self.assertDictEqual(actual_coeffs_g2, expected_coeffs_g2_ge_map)
        else:
            self.fail(f"Unexpected constraint sense for {unit_g2}: {constr_g2.Sense}")

        # Clean up: remove constraints
        self.model.remove(constrs)

    def test_add_c_ramp_down(self):
        """Test the add_c_ramp_down constraint function for t > 1."""
        # Define local test data for RD and SD rates
        rd_data = {"G1": 20, "G2": 30}  # Ramp-down rate
        sd_data = {"G1": 60, "G2": 120}  # Shutdown capability (P_sd)

        constrs = thermal_unit_constr.add_c_ramp_down(
            model=self.model,
            p=self.p_vars,
            u=self.u_vars,
            w=self.w_vars,
            sim_horizon=self.sim_horizon_3,
            thermal_units=self.thermal_units,
            thermal_min_capacity=self.thermal_min_capacity_data,
            RD=rd_data,
            SD=sd_data,
        )
        self.model.update()

        # Check the number of constraints added

        expected_num_constrs = len(self.thermal_units) * (self.sim_horizon_3 - 1)
        self.assertEqual(len(constrs), expected_num_constrs)

        # --- Test Constraint for G1, t = 2 (first applicable timestep) ---
        unit_g1 = "G1"
        t_val = 2
        # Constraint from function:
        # p[G1,1] - p[G1,2] <= (SD[G1] - min_cap[G1] - RD[G1]) * w[G1,2] + RD[G1] * u[G1,1]
        # Rearranged for Gurobi (variables on LHS, constants on RHS, for sense <=, RHS=0):
        # p[G1,1] - p[G1,2] - (SD[G1] - min_cap[G1] - RD[G1]) * w[G1,2] - RD[G1] * u[G1,1] <= 0
        # which means:
        # 1.0 * p[G1,1]
        # -1.0 * p[G1,2]
        # + (RD[G1] + min_cap[G1] - SD[G1]) * w[G1,2]
        # - RD[G1] * u[G1,1]
        # <= 0

        constr_g1_t2 = self.model.getConstrByName(f"rampDown[{unit_g1},{t_val}]")

        # Calculate expected coefficients and RHS for G1, t=2
        expected_p_t_minus_1_coeff_le = 1.0
        expected_p_t_coeff_le = -1.0
        expected_w_t_coeff_le = (
            rd_data[unit_g1]
            + self.thermal_min_capacity_data[unit_g1]
            - sd_data[unit_g1]
        )  # 20 + 50 - 60 = 10
        expected_u_t_minus_1_coeff_le = -rd_data[unit_g1]  # -20
        expected_rhs = 0.0

        self.assertIn(constr_g1_t2.Sense, [gp.GRB.LESS_EQUAL, gp.GRB.GREATER_EQUAL])
        self.assertAlmostEqual(
            constr_g1_t2.RHS, expected_rhs
        )  # RHS should be 0.0 even if flipped

        row_g1_t2 = self.model.getRow(constr_g1_t2)

        expected_coeffs_g1_t2_le_map = {}
        # p[G1,1]
        if abs(expected_p_t_minus_1_coeff_le) > 1e-9:
            expected_coeffs_g1_t2_le_map[self.p_vars[unit_g1, t_val - 1].VarName] = (
                expected_p_t_minus_1_coeff_le
            )
        # p[G1,2]
        if abs(expected_p_t_coeff_le) > 1e-9:
            expected_coeffs_g1_t2_le_map[self.p_vars[unit_g1, t_val].VarName] = (
                expected_p_t_coeff_le
            )
        # w[G1,2]
        if abs(expected_w_t_coeff_le) > 1e-9:
            expected_coeffs_g1_t2_le_map[self.w_vars[unit_g1, t_val].VarName] = (
                expected_w_t_coeff_le
            )
        # u[G1,1]
        if abs(expected_u_t_minus_1_coeff_le) > 1e-9:
            expected_coeffs_g1_t2_le_map[self.u_vars[unit_g1, t_val - 1].VarName] = (
                expected_u_t_minus_1_coeff_le
            )

        self.assertEqual(row_g1_t2.size(), len(expected_coeffs_g1_t2_le_map))

        actual_coeffs_g1_t2 = {}
        if row_g1_t2.size() > 0:
            for i in range(row_g1_t2.size()):
                var = row_g1_t2.getVar(i)
                actual_coeffs_g1_t2[var.VarName] = row_g1_t2.getCoeff(i)

        if constr_g1_t2.Sense == gp.GRB.LESS_EQUAL:
            self.assertDictEqual(actual_coeffs_g1_t2, expected_coeffs_g1_t2_le_map)
        elif constr_g1_t2.Sense == gp.GRB.GREATER_EQUAL:  # Gurobi flipped everything
            expected_coeffs_g1_t2_ge_map = {
                k: -v for k, v in expected_coeffs_g1_t2_le_map.items()
            }
            self.assertDictEqual(actual_coeffs_g1_t2, expected_coeffs_g1_t2_ge_map)
        else:
            self.fail(
                f"Unexpected constraint sense for {constr_g1_t2}: {constr_g1_t2.Sense}"
            )

        # Clean up: remove constraints
        self.model.remove(constrs)

    def test_add_c_ramp_up_init(self):
        """Test the add_c_ramp_up_init constraint function."""

        # Define local test data
        initial_p_data = {"G1": 10, "G2": 0}  # Initial power above min capacity (t=0)
        # G1 is on, G2 is at Pmin or off
        ru_data = {"G1": 20, "G2": 30}  # Ramp-up rate
        # Adjusted SU_data for G1 to ensure v_coeff is non-zero for testing
        su_data = {
            "G1": 60,
            "G2": 120,
        }  # Startup capability (max power output when starting up)

        constrs = thermal_unit_constr.add_c_ramp_up_init(
            model=self.model,
            pbar=self.pbar_vars,
            u=self.u_vars,
            v=self.v_vars,
            thermal_units=self.thermal_units,
            initial_p=initial_p_data,
            thermal_min_capacity=self.thermal_min_capacity_data,
            RU=ru_data,
            SU=su_data,
        )
        self.model.update()

        # Check the number of constraints added
        self.assertEqual(len(constrs), len(self.thermal_units))

        # --- Test Constraint for G1 ---
        unit_g1 = "G1"
        # Constraint: pbar[G1,1] - initial_p[G1] <= (SU[G1] - min_cap[G1] - RU[G1]) * v[G1,1] + RU[G1] * u[G1,1]
        # Rearranged for Gurobi (variables on LHS, constants on RHS, for sense <=):
        # pbar[G1,1] - (SU[G1] - min_cap[G1] - RU[G1]) * v[G1,1] - RU[G1] * u[G1,1] <= initial_p[G1]
        # which is:
        # 1.0 * pbar[G1,1]
        # + (RU[G1] + min_cap[G1] - SU[G1]) * v[G1,1]
        # - RU[G1] * u[G1,1]
        # <= initial_p[G1]

        constr_g1 = constrs.get(unit_g1)
        self.assertIsNotNone(constr_g1, f"Constraint for {unit_g1} not found.")

        # Calculate expected coefficients and RHS for G1
        expected_pbar_coeff_g1_le = 1.0
        expected_v_coeff_g1_le = (
            ru_data[unit_g1]
            + self.thermal_min_capacity_data[unit_g1]
            - su_data[unit_g1]
        )  # 20 + 50 - 60 = 10
        expected_u_coeff_g1_le = -ru_data[unit_g1]  # -20
        expected_rhs_g1 = initial_p_data[unit_g1]  # 10

        self.assertIn(constr_g1.Sense, [gp.GRB.LESS_EQUAL, gp.GRB.GREATER_EQUAL])

        row_g1 = self.model.getRow(constr_g1)

        expected_coeffs_g1_le_map = {}
        num_expected_terms_g1 = 0
        if abs(expected_pbar_coeff_g1_le) > 1e-9:
            expected_coeffs_g1_le_map[self.pbar_vars[unit_g1, 1].VarName] = (
                expected_pbar_coeff_g1_le
            )
            num_expected_terms_g1 += 1
        if abs(expected_v_coeff_g1_le) > 1e-9:
            expected_coeffs_g1_le_map[self.v_vars[unit_g1, 1].VarName] = (
                expected_v_coeff_g1_le
            )
            num_expected_terms_g1 += 1
        if abs(expected_u_coeff_g1_le) > 1e-9:
            expected_coeffs_g1_le_map[self.u_vars[unit_g1, 1].VarName] = (
                expected_u_coeff_g1_le
            )
            num_expected_terms_g1 += 1

        self.assertEqual(row_g1.size(), num_expected_terms_g1)

        actual_coeffs_g1 = {}
        if row_g1.size() > 0:
            for i in range(row_g1.size()):
                var = row_g1.getVar(i)
                actual_coeffs_g1[var.VarName] = row_g1.getCoeff(i)

        if constr_g1.Sense == gp.GRB.LESS_EQUAL:
            self.assertAlmostEqual(constr_g1.RHS, expected_rhs_g1)
            self.assertDictEqual(actual_coeffs_g1, expected_coeffs_g1_le_map)
        elif constr_g1.Sense == gp.GRB.GREATER_EQUAL:
            self.assertAlmostEqual(constr_g1.RHS, -expected_rhs_g1)
            expected_coeffs_g1_ge_map = {
                k: -v for k, v in expected_coeffs_g1_le_map.items()
            }
            self.assertDictEqual(actual_coeffs_g1, expected_coeffs_g1_ge_map)
        else:
            self.fail(f"Unexpected constraint sense for {unit_g1}: {constr_g1.Sense}")

        # --- Test Constraint for G2 ---
        unit_g2 = "G2"
        constr_g2 = constrs.get(unit_g2)
        self.assertIsNotNone(constr_g2, f"Constraint for {unit_g2} not found.")

        expected_pbar_coeff_g2_le = 1.0
        expected_v_coeff_g2_le = (
            ru_data[unit_g2]
            + self.thermal_min_capacity_data[unit_g2]
            - su_data[unit_g2]
        )  # 30 + 100 - 120 = 10
        expected_u_coeff_g2_le = -ru_data[unit_g2]  # -30
        expected_rhs_g2 = initial_p_data[unit_g2]  # 0

        self.assertIn(constr_g2.Sense, [gp.GRB.LESS_EQUAL, gp.GRB.GREATER_EQUAL])
        row_g2 = self.model.getRow(constr_g2)

        expected_coeffs_g2_le_map = {}
        num_expected_terms_g2 = 0
        if abs(expected_pbar_coeff_g2_le) > 1e-9:
            expected_coeffs_g2_le_map[self.pbar_vars[unit_g2, 1].VarName] = (
                expected_pbar_coeff_g2_le
            )
            num_expected_terms_g2 += 1
        if abs(expected_v_coeff_g2_le) > 1e-9:
            expected_coeffs_g2_le_map[self.v_vars[unit_g2, 1].VarName] = (
                expected_v_coeff_g2_le
            )
            num_expected_terms_g2 += 1
        if abs(expected_u_coeff_g2_le) > 1e-9:
            expected_coeffs_g2_le_map[self.u_vars[unit_g2, 1].VarName] = (
                expected_u_coeff_g2_le
            )
            num_expected_terms_g2 += 1

        self.assertEqual(row_g2.size(), num_expected_terms_g2)

        actual_coeffs_g2 = {}
        if row_g2.size() > 0:
            for i in range(row_g2.size()):
                var = row_g2.getVar(i)
                actual_coeffs_g2[var.VarName] = row_g2.getCoeff(i)

        if constr_g2.Sense == gp.GRB.LESS_EQUAL:
            self.assertAlmostEqual(constr_g2.RHS, expected_rhs_g2)
            self.assertDictEqual(actual_coeffs_g2, expected_coeffs_g2_le_map)
        elif constr_g2.Sense == gp.GRB.GREATER_EQUAL:
            self.assertAlmostEqual(constr_g2.RHS, -expected_rhs_g2)
            expected_coeffs_g2_ge_map = {
                k: -v for k, v in expected_coeffs_g2_le_map.items()
            }
            self.assertDictEqual(actual_coeffs_g2, expected_coeffs_g2_ge_map)
        else:
            self.fail(f"Unexpected constraint sense for {unit_g2}: {constr_g2.Sense}")

        # Clean up
        self.model.remove(constrs)

    # In your TestThermalUnitConstraints class:

    def test_add_c_ramp_up(self):
        """Test the add_c_ramp_up constraint function for t > 1."""
        # Define local test data for RU and SU rates
        ru_data = {"G1": 20, "G2": 30}  # Ramp-up rate
        # Using SU_data that makes coefficient for v_vars non-zero
        su_data = {"G1": 60, "G2": 120}  # Startup capability

        constrs = thermal_unit_constr.add_c_ramp_up(
            model=self.model,
            p=self.p_vars,
            pbar=self.pbar_vars,
            u=self.u_vars,
            v=self.v_vars,
            sim_horizon=self.sim_horizon_3,
            thermal_units=self.thermal_units,
            thermal_min_capacity=self.thermal_min_capacity_data,
            RU=ru_data,
            SU=su_data,
        )
        self.model.update()

        # Check the number of constraints added
        expected_num_constrs = 0
        if self.sim_horizon_3 >= 2:
            expected_num_constrs = len(self.thermal_units) * (
                self.sim_horizon_3 - 1
            )  # t from 2 to sim_horizon

        self.assertEqual(len(constrs), expected_num_constrs)

        # --- Test Constraint for G1, t = 2 (first applicable timestep) ---
        unit_g1 = "G1"
        t_val = 2
        # Constraint from function:
        # pbar[G1,2] - p[G1,1] <= (SU[G1] - min_cap[G1] - RU[G1]) * v[G1,2] + RU[G1] * u[G1,2]
        # Rearranged for Gurobi (variables on LHS, constants on RHS, for sense <=, RHS=0):
        # 1.0 * pbar[G1,2]
        # -1.0 * p[G1,1]
        # + (RU[G1] + min_cap[G1] - SU[G1]) * v[G1,2]
        # - RU[G1] * u[G1,2]
        # <= 0

        constr_g1_t2_key = (unit_g1, t_val)
        constr_g1_t2 = constrs.get(constr_g1_t2_key)
        self.assertIsNotNone(
            constr_g1_t2, f"Constraint for {constr_g1_t2_key} not found."
        )

        # Calculate expected coefficients and RHS for G1, t=2
        expected_pbar_t_coeff_le = 1.0
        expected_p_t_minus_1_coeff_le = -1.0
        expected_v_t_coeff_le = (
            ru_data[unit_g1]
            + self.thermal_min_capacity_data[unit_g1]
            - su_data[unit_g1]
        )  # 20 + 50 - 60 = 10
        expected_u_t_coeff_le = -ru_data[unit_g1]  # -20
        expected_rhs = 0.0

        self.assertIn(constr_g1_t2.Sense, [gp.GRB.LESS_EQUAL, gp.GRB.GREATER_EQUAL])
        self.assertAlmostEqual(constr_g1_t2.RHS, expected_rhs)

        row_g1_t2 = self.model.getRow(constr_g1_t2)

        expected_coeffs_g1_t2_le_map = {}
        # pbar[G1,2]
        if abs(expected_pbar_t_coeff_le) > 1e-9:
            expected_coeffs_g1_t2_le_map[self.pbar_vars[unit_g1, t_val].VarName] = (
                expected_pbar_t_coeff_le
            )
        # p[G1,1]
        if abs(expected_p_t_minus_1_coeff_le) > 1e-9:
            expected_coeffs_g1_t2_le_map[self.p_vars[unit_g1, t_val - 1].VarName] = (
                expected_p_t_minus_1_coeff_le
            )
        # v[G1,2]
        if abs(expected_v_t_coeff_le) > 1e-9:
            expected_coeffs_g1_t2_le_map[self.v_vars[unit_g1, t_val].VarName] = (
                expected_v_t_coeff_le
            )
        # u[G1,2]
        if abs(expected_u_t_coeff_le) > 1e-9:
            expected_coeffs_g1_t2_le_map[self.u_vars[unit_g1, t_val].VarName] = (
                expected_u_t_coeff_le
            )

        self.assertEqual(row_g1_t2.size(), len(expected_coeffs_g1_t2_le_map))

        actual_coeffs_g1_t2 = {}
        if row_g1_t2.size() > 0:
            for i in range(row_g1_t2.size()):
                var = row_g1_t2.getVar(i)
                actual_coeffs_g1_t2[var.VarName] = row_g1_t2.getCoeff(i)

        if constr_g1_t2.Sense == gp.GRB.LESS_EQUAL:
            self.assertDictEqual(actual_coeffs_g1_t2, expected_coeffs_g1_t2_le_map)
        elif constr_g1_t2.Sense == gp.GRB.GREATER_EQUAL:
            expected_coeffs_g1_t2_ge_map = {
                k: -v for k, v in expected_coeffs_g1_t2_le_map.items()
            }
            self.assertDictEqual(actual_coeffs_g1_t2, expected_coeffs_g1_t2_ge_map)
        else:
            self.fail(
                f"Unexpected constraint sense for {constr_g1_t2_key}: {constr_g1_t2.Sense}"
            )

        # Clean up
        self.model.remove(constrs)

    def tearDown(self):
        # Dispose of the model to free Gurobi resources
        self.model.dispose()


if __name__ == "__main__":
    unittest.main()
