"""test_thermal_unit_constr.py"""

import unittest
import gurobipy as gp

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

        self.initial_u_data = {"G1": 0, "G2": 1}
        self.thermal_min_capacity_data = {"G1": 50, "G2": 100}

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

        row = self.model.getRow(specific_constr)

        # Check number of non-zero coefficients in the LHS
        self.assertEqual(row.size(), 2)

        # Check which variables are involved in the LHS
        actual_var_names = {row.getVar(i).VarName for i in range(row.size())}
        expected_var_names = {
            self.pthermal_vars[test_unit, test_t].VarName,
            self.u_vars[test_unit, test_t].VarName,
        }
        self.assertSetEqual(actual_var_names, expected_var_names)
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

    def tearDown(self):
        # Dispose of the model to free Gurobi resources
        self.model.dispose()


if __name__ == "__main__":
    unittest.main()
