"""test_system_constr.py: Unittests for system-wide constraints."""

import math
import unittest

import gurobipy as gp
import pandas as pd

from pownet.optim_model.constraints import system_constr


class TestSystemConstraints(unittest.TestCase):
    """Test cases for system-wide constraints."""

    def setUp(self):
        """Set up common resources for each test method."""
        self.model = gp.Model("test_system_constraints")
        self.model.setParam("OutputFlag", 0)  # Suppress Gurobi output

        self.nodes = ["N1", "N2", "N3"]
        self.thermal_units = ["G1", "G2"]
        self.storage_units = ["S1"]
        self.edges = [
            ("N1", "N2"),
            ("N1", "N3"),
            ("N2", "N3"),
        ]  # List of network edges (branches)
        self.max_demand_node_name = "N1"

        self.sim_horizon = 3
        self.timesteps = range(1, self.sim_horizon + 1)  # Timesteps: 1, 2, 3

        # Corresponds to the '24' in susceptance lookup: t + (step_k - 1) * 24
        self.hours_per_step = 24

        # Variables for add_c_reserve_req_1
        self.spin_vars = self.model.addVars(
            self.thermal_units,
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            lb=0,
            name="spin",
        )

        # Variables for add_c_reserve_req_2
        self.pbar_vars = self.model.addVars(
            self.thermal_units,
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            lb=0,
            name="pbar",
        )
        self.u_vars = self.model.addVars(
            self.thermal_units, self.timesteps, vtype=gp.GRB.BINARY, name="u"
        )
        self.thermal_min_capacity_data = {"G1": 50.0, "G2": 30.0}

        # Common variables for reserve constraints
        self.charge_state_vars = self.model.addVars(
            self.storage_units,
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            lb=0,
            name="charge_state",
        )
        self.spin_shortfall_vars = self.model.addVars(
            self.timesteps, vtype=gp.GRB.CONTINUOUS, lb=0, name="spin_shortfall"
        )

        # Variables for add_c_link_shortfall
        self.load_shortfall_vars = self.model.addVars(
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            name="load_shortfall",
            lb=-gp.GRB.INFINITY,
        )
        self.p_pmismatch_vars = self.model.addVars(
            self.timesteps, vtype=gp.GRB.CONTINUOUS, lb=0, name="p_pmismatch"
        )
        self.n_pmismatch_vars = self.model.addVars(
            self.timesteps, vtype=gp.GRB.CONTINUOUS, lb=0, name="n_pmismatch"
        )

        # Variables for voltage angle constraints (ref_node and angle_diff)
        self.theta_vars = self.model.addVars(
            self.nodes,
            self.timesteps,
            vtype=gp.GRB.CONTINUOUS,
            name="theta",
            lb=-math.pi / 2,
            ub=math.pi / 2,
        )

        # Variables for add_c_angle_diff
        self.flow_fwd_vars = gp.tupledict()
        self.flow_bwd_vars = gp.tupledict()
        for a_node, b_node in self.edges:
            for t_step in self.timesteps:
                key = (a_node, b_node, t_step)
                self.flow_fwd_vars[key] = self.model.addVar(
                    vtype=gp.GRB.CONTINUOUS,
                    name=f"flow_fwd_{a_node}_{b_node}_{t_step}",
                    lb=-gp.GRB.INFINITY,
                )
                self.flow_bwd_vars[key] = self.model.addVar(
                    vtype=gp.GRB.CONTINUOUS,
                    name=f"flow_bwd_{a_node}_{b_node}_{t_step}",
                    lb=-gp.GRB.INFINITY,
                )

        self.model.update()

    def tearDown(self):
        """Clean up resources after each test method."""
        self.model.dispose()

    def test_add_c_reserve_req_1(self):
        """Test reserve requirement constraint for step_k = 1 with non-empty units and timesteps."""
        step_k = 1  # Test case specifically for step_k = 1

        # For step_k=1, spin_requirement indices are t + (1-1)*24 = t
        # For timesteps 1, 2, 3, indices for spin_requirement_series.loc will be 1, 2, 3
        spin_req_data = {t: 100.0 + t * 10.0 for t in self.timesteps}
        spin_requirement_series = pd.Series(spin_req_data)

        constrs = system_constr.add_c_reserve_req_1(
            model=self.model,
            spin=self.spin_vars,
            charge_state=self.charge_state_vars,
            spin_shortfall=self.spin_shortfall_vars,
            timesteps=self.timesteps,  # Using non-empty timesteps from setUp
            step_k=step_k,
            thermal_units=self.thermal_units,  # Using non-empty thermal_units from setUp
            storage_units=self.storage_units,  # Using non-empty storage_units from setUp
            spin_requirement=spin_requirement_series,
        )
        self.model.update()

        self.assertEqual(
            len(constrs),
            len(list(self.timesteps)),
            "Incorrect number of constraints added.",
        )

        for t in self.timesteps:
            # Gurobi names constraints from addConstrs like "name[index]"
            constr_name = f"reserveReq1[{t}]"
            current_constr = self.model.getConstrByName(constr_name)

            self.assertIsNotNone(current_constr, f"Constraint {constr_name} not found.")
            self.assertEqual(
                current_constr.Sense,
                gp.GRB.GREATER_EQUAL,
                f"Incorrect sense for {constr_name}.",
            )

            # For step_k = 1, expected_rhs_idx is just 't'
            expected_rhs_idx = t + (step_k - 1) * self.hours_per_step
            expected_rhs = spin_requirement_series.loc[expected_rhs_idx]
            self.assertAlmostEqual(
                current_constr.RHS,
                expected_rhs,
                msg=f"Incorrect RHS for {constr_name}.",
            )

            row = self.model.getRow(current_constr)
            actual_coeffs = {
                row.getVar(i).VarName: row.getCoeff(i) for i in range(row.size())
            }

            expected_coeffs = {}
            for unit in self.thermal_units:  # Iterating over non-empty thermal_units
                expected_coeffs[self.spin_vars[unit, t].VarName] = 1.0
            for unit in self.storage_units:  # Iterating over non-empty storage_units
                expected_coeffs[self.charge_state_vars[unit, t].VarName] = 1.0
            expected_coeffs[self.spin_shortfall_vars[t].VarName] = 1.0

            self.assertDictEqual(
                actual_coeffs,
                expected_coeffs,
                f"Incorrect coefficients for {constr_name}.",
            )

        # Clean up
        self.model.remove(constrs)

    def test_add_c_reserve_req_2(self):
        """Test reserve requirement constraint (formulation 2) for step_k = 1."""
        step_k = 1

        # Data for RHS terms
        total_demand_data = {t: 1000.0 + t * 50.0 for t in self.timesteps}
        total_demand_series = pd.Series(total_demand_data)

        spin_requirement_data = {t: 100.0 + t * 5.0 for t in self.timesteps}
        spin_requirement_series = pd.Series(spin_requirement_data)

        constrs = system_constr.add_c_reserve_req_2(
            model=self.model,
            pbar=self.pbar_vars,
            u=self.u_vars,
            charge_state=self.charge_state_vars,
            spin_shortfall=self.spin_shortfall_vars,
            timesteps=self.timesteps,
            step_k=step_k,
            thermal_units=self.thermal_units,
            thermal_min_capacity=self.thermal_min_capacity_data,
            storage_units=self.storage_units,
            total_demand=total_demand_series,
            spin_requirement=spin_requirement_series,
        )
        self.model.update()

        self.assertEqual(
            len(constrs),
            len(list(self.timesteps)),
            "Incorrect number of constraints for reserveReq2.",
        )

        for t in self.timesteps:
            constr_name = f"reserveReq2[{t}]"  # Name specified in the function
            current_constr = self.model.getConstrByName(constr_name)

            self.assertIsNotNone(current_constr, f"Constraint {constr_name} not found.")
            self.assertEqual(
                current_constr.Sense,
                gp.GRB.GREATER_EQUAL,
                f"Incorrect sense for {constr_name}.",
            )

            idx = (
                t + (step_k - 1) * self.hours_per_step
            )  # Simplifies to 't' for step_k=1
            expected_rhs = (
                total_demand_series.loc[idx] + spin_requirement_series.loc[idx]
            )
            self.assertAlmostEqual(
                current_constr.RHS,
                expected_rhs,
                msg=f"Incorrect RHS for {constr_name}.",
            )

            row = self.model.getRow(current_constr)
            actual_coeffs = {
                row.getVar(i).VarName: row.getCoeff(i) for i in range(row.size())
            }

            expected_coeffs = {}
            # Thermal unit contributions
            for unit in self.thermal_units:
                expected_coeffs[self.pbar_vars[unit, t].VarName] = 1.0
                expected_coeffs[self.u_vars[unit, t].VarName] = (
                    self.thermal_min_capacity_data[unit]
                )
            # Storage unit contributions
            for unit in self.storage_units:
                expected_coeffs[self.charge_state_vars[unit, t].VarName] = 1.0
            # Spin shortfall
            expected_coeffs[self.spin_shortfall_vars[t].VarName] = 1.0

            self.assertDictEqual(
                actual_coeffs,
                expected_coeffs,
                f"Incorrect coefficients for {constr_name}.",
            )

        # Clean up
        self.model.remove(constrs)

    def test_add_c_link_shortfall(self):
        """Test the linking constraint for load shortfall."""

        constrs = system_constr.add_c_link_shortfall(
            model=self.model,
            load_shortfall=self.load_shortfall_vars,
            p_pmismatch=self.p_pmismatch_vars,
            n_pmismatch=self.n_pmismatch_vars,
            timesteps=self.timesteps,
        )
        self.model.update()

        self.assertEqual(
            len(constrs),
            len(list(self.timesteps)),
            "Incorrect number of constraints for link_shortfall.",
        )

        for t in self.timesteps:
            # Constraints are returned in a tupledict keyed by timestep
            current_constr = constrs[t]

            self.assertIsNotNone(
                current_constr,
                f"Constraint for link_shortfall at timestep {t} not found.",
            )
            self.assertEqual(
                current_constr.Sense,
                gp.GRB.EQUAL,
                f"Incorrect sense for link_shortfall at t={t}.",
            )

            # Expected: load_shortfall[t] - p_pmismatch[t] + n_pmismatch[t] == 0
            self.assertAlmostEqual(
                current_constr.RHS,
                0.0,
                msg=f"Incorrect RHS for link_shortfall at t={t}.",
            )

            row = self.model.getRow(current_constr)
            actual_coeffs = {
                row.getVar(i).VarName: row.getCoeff(i) for i in range(row.size())
            }

            expected_coeffs = {
                self.load_shortfall_vars[t].VarName: 1.0,
                self.p_pmismatch_vars[t].VarName: -1.0,
                self.n_pmismatch_vars[t].VarName: 1.0,
            }

            self.assertDictEqual(
                actual_coeffs,
                expected_coeffs,
                f"Incorrect coefficients for link_shortfall at t={t}.",
            )

        self.model.remove(constrs)

    def test_add_c_ref_node(self):
        """Test the reference node voltage angle constraint."""
        constrs = system_constr.add_c_ref_node(
            model=self.model,
            theta=self.theta_vars,
            timesteps=self.timesteps,
            max_demand_node=self.max_demand_node_name,
        )
        self.model.update()
        self.assertEqual(len(constrs), len(list(self.timesteps)))
        for t in self.timesteps:
            constr_name = f"refNode[{t}]"
            current_constr = self.model.getConstrByName(constr_name)
            self.assertIsNotNone(current_constr)
            self.assertEqual(current_constr.Sense, gp.GRB.EQUAL)
            self.assertAlmostEqual(current_constr.RHS, 0.0)
            row = self.model.getRow(current_constr)
            actual_coeffs = {
                row.getVar(i).VarName: row.getCoeff(i) for i in range(row.size())
            }
            expected_coeffs = {
                self.theta_vars[self.max_demand_node_name, t].VarName: 1.0
            }
            self.assertDictEqual(actual_coeffs, expected_coeffs)
        self.model.remove(constrs)

    def test_add_c_angle_diff(self):
        """Test the DC power flow equation based on angle differences."""
        step_k = 1

        # Create susceptance DataFrame
        # Rows: time_indices based on step_k and timesteps. Columns: edges (tuples (a,b)).
        sus_data_for_df = {}
        example_base_susceptance = 10.0  # Ensure non-zero susceptance
        for t_model_idx in self.timesteps:
            # df_time_idx is the actual index used for .loc in the susceptance DataFrame
            df_time_idx = t_model_idx + (step_k - 1) * self.hours_per_step

            edge_data_for_this_time = {}
            for edge_idx, edge_tuple in enumerate(self.edges):
                # Create some unique, non-zero susceptance value for testing
                sus_val = example_base_susceptance + edge_idx + (t_model_idx / 10.0)
                edge_data_for_this_time[edge_tuple] = sus_val
            sus_data_for_df[df_time_idx] = edge_data_for_this_time

        susceptance_df = pd.DataFrame.from_dict(sus_data_for_df, orient="index")
        # Ensure columns are tuples (edge_tuple) if not already. Pandas should handle this.

        constrs = system_constr.add_c_angle_diff(
            model=self.model,
            flow_fwd=self.flow_fwd_vars,
            flow_bwd=self.flow_bwd_vars,
            theta=self.theta_vars,
            timesteps=self.timesteps,
            step_k=step_k,
            edges=self.edges,
            susceptance=susceptance_df,
        )
        self.model.update()

        self.assertEqual(
            len(constrs),
            len(self.edges) * len(list(self.timesteps)),
            "Incorrect number of angleDiff constraints.",
        )

        for a_node, b_node in self.edges:
            for t_step in self.timesteps:
                constr_name = f"angleDiff[{a_node},{b_node},{t_step}]"
                current_constr = self.model.getConstrByName(constr_name)

                self.assertIsNotNone(
                    current_constr, f"Constraint {constr_name} not found."
                )
                self.assertEqual(
                    current_constr.Sense,
                    gp.GRB.EQUAL,
                    f"Incorrect sense for {constr_name}.",
                )
                self.assertAlmostEqual(
                    current_constr.RHS, 0.0, msg=f"Incorrect RHS for {constr_name}."
                )

                # Constraint form: flow_fwd - flow_bwd - B*(theta_a - theta_b) == 0
                # So: 1*flow_fwd - 1*flow_bwd - B*theta_a + B*theta_b == 0

                df_time_idx = t_step + (step_k - 1) * self.hours_per_step
                susceptance_val = susceptance_df.loc[df_time_idx, (a_node, b_node)]

                row = self.model.getRow(current_constr)
                actual_coeffs = {
                    row.getVar(i).VarName: row.getCoeff(i) for i in range(row.size())
                }

                expected_coeffs = {
                    self.flow_fwd_vars[a_node, b_node, t_step].VarName: 1.0,
                    self.flow_bwd_vars[a_node, b_node, t_step].VarName: -1.0,
                    self.theta_vars[a_node, t_step].VarName: -susceptance_val,
                    self.theta_vars[b_node, t_step].VarName: susceptance_val,
                }

                self.assertDictEqual(
                    actual_coeffs,
                    expected_coeffs,
                    f"Incorrect coefficients for {constr_name}.",
                )

        self.model.remove(constrs)


##########################################################################
# Tests for add_c_flow_balance function
##########################################################################


class TestAddCFlowBalance(unittest.TestCase):
    """Test cases for the add_c_flow_balance constraint function."""

    def setUp(self):
        """Set up common resources for each test method."""
        self.model = gp.Model("test_flow_balance")
        self.model.setParam("OutputFlag", 0)  # Suppress Gurobi output

        self.nodes = ["N1", "N2", "N3"]
        self.timesteps = range(1, 3)  # Timesteps: 1, 2
        self.hours_per_step = 24  # Standard in the tested function for demand lookup

        # --- Define topology and unit assignments ---
        self.thermal_units = ["G_therm_N1_1", "G_therm_N2_1"]
        self.hydro_units = ["H_hydro_N2_1"]
        self.solar_units = ["S_solar_N1_1"]
        self.wind_units = []  # Test with empty type
        self.import_units = ["I_import_N3_1"]

        self.node_generator = {n: [] for n in self.nodes}
        self.node_generator["N1"] = ["G_therm_N1_1", "S_solar_N1_1"]
        self.node_generator["N2"] = ["G_therm_N2_1", "H_hydro_N2_1"]
        self.node_generator["N3"] = ["I_import_N3_1"]

        self.storage_unit_names = ["ESS_N1", "ESS_N2"]
        self.ess_charge_units = {
            "N1": ["ESS_N1"],
            "N2": ["ESS_N2"],
        }  # ESS_N1 charges from N1, ESS_N2 from N2
        self.ess_discharge_units = {
            "N1": ["ESS_N1"],
            "N2": ["ESS_N2"],
        }  # ESS_N1 discharges to N1, ESS_N2 to N2
        # N3 has no storage connected in this setup.

        self.edges = [("N1", "N2"), ("N1", "N3")]  # N2 is not connected to N3 directly
        self.node_edge = {n: [] for n in self.nodes}
        for u, v_node in self.edges:  # Corrected variable name v to v_node
            self.node_edge[u].append((u, v_node))
            self.node_edge[v_node].append((u, v_node))
        # node_edge structure:
        # N1: [("N1", "N2"), ("N1", "N3")]
        # N2: [("N1", "N2")]
        # N3: [("N1", "N3")]

        self.demand_nodes = ["N1", "N2", "N3"]  # All nodes have demand

        # --- Demand DataFrame ---
        # Max step_k=2, max t in self.timesteps is 2 (range(1,3)).
        # Indices needed: for step_k=1 -> 1, 2. For step_k=2 -> 1+24=25, 2+24=26.
        _demand_abs_indices = sorted(
            list(
                set(
                    [
                        t + (k - 1) * self.hours_per_step
                        for t in self.timesteps
                        for k in [1, 2]
                    ]
                )
            )
        )  # Generates [1, 2, 25, 26]

        _demand_data = {}
        for node_idx, node_name in enumerate(self.nodes):
            # Create some arbitrary demand values
            _demand_data[node_name] = {
                t_abs: (100 + 10 * t_abs + 5 * node_idx)
                for t_abs in _demand_abs_indices
            }
        self.demand_df = pd.DataFrame(_demand_data, index=_demand_abs_indices)

        # --- Loss Factors ---
        self.gen_loss_factor = 0.08
        self.line_loss_factor = 0.03
        self.gen_efficiency = 1 - self.gen_loss_factor
        self.line_efficiency = 1 - self.line_loss_factor

        # --- Gurobi Variables ---
        # Generation variables
        self.pthermal = self.model.addVars(
            self.thermal_units, self.timesteps, name="pthermal", lb=0
        )
        self.phydro = self.model.addVars(
            self.hydro_units, self.timesteps, name="phydro", lb=0
        )
        self.psolar = self.model.addVars(
            self.solar_units, self.timesteps, name="psolar", lb=0
        )
        self.pwind = self.model.addVars(
            self.wind_units, self.timesteps, name="pwind", lb=0
        )  # Empty tupledict
        self.pimp = self.model.addVars(
            self.import_units, self.timesteps, name="pimp", lb=0
        )

        # Storage variables
        self.pcharge = self.model.addVars(
            self.storage_unit_names, self.timesteps, name="pcharge", lb=0
        )
        self.pdis = self.model.addVars(
            self.storage_unit_names, self.timesteps, name="pdis", lb=0
        )

        # Mismatch (slack) variables
        self.pos_pmismatch = self.model.addVars(
            self.nodes, self.timesteps, name="pos_pmismatch", lb=0
        )
        self.neg_pmismatch = self.model.addVars(
            self.nodes, self.timesteps, name="neg_pmismatch", lb=0
        )

        # Flow variables
        self.flow_fwd = gp.tupledict()  # flow_fwd[k,s,t] is flow k -> s
        self.flow_bwd = (
            gp.tupledict()
        )  # flow_bwd[k,s,t] is flow s -> k (on edge defined as k-s)
        for u, v_node in self.edges:  # Corrected variable name v to v_node
            for t_step in self.timesteps:
                key = (u, v_node, t_step)
                self.flow_fwd[key] = self.model.addVar(
                    name=f"flow_fwd_{u}_{v_node}_{t_step}", lb=-gp.GRB.INFINITY
                )
                self.flow_bwd[key] = self.model.addVar(
                    name=f"flow_bwd_rev_{u}_{v_node}_{t_step}", lb=-gp.GRB.INFINITY
                )

        self.model.update()

    def tearDown(self):
        """Clean up resources after each test method."""
        self.model.dispose()

    def _run_test_for_step_k(self, step_k: int):
        """Helper method to run tests for a given step_k."""

        # Call the function to add constraints
        constrs = system_constr.add_c_flow_balance(
            model=self.model,
            pthermal=self.pthermal,
            phydro=self.phydro,
            psolar=self.psolar,
            pwind=self.pwind,
            pimp=self.pimp,
            pcharge=self.pcharge,
            pdis=self.pdis,
            pos_pmismatch=self.pos_pmismatch,
            neg_pmismatch=self.neg_pmismatch,
            flow_fwd=self.flow_fwd,
            flow_bwd=self.flow_bwd,
            timesteps=self.timesteps,
            step_k=step_k,
            thermal_units=self.thermal_units,
            hydro_units=self.hydro_units,
            solar_units=self.solar_units,
            wind_units=self.wind_units,
            import_units=self.import_units,
            nodes=self.nodes,
            node_edge=self.node_edge,
            node_generator=self.node_generator,
            ess_charge_units=self.ess_charge_units,
            ess_discharge_units=self.ess_discharge_units,
            demand_nodes=self.demand_nodes,
            demand=self.demand_df,
            gen_loss_factor=self.gen_loss_factor,
            line_loss_factor=self.line_loss_factor,
        )
        self.model.update()

        # 1. Check the number of constraints added
        expected_num_constrs = len(self.nodes) * len(list(self.timesteps))
        self.assertEqual(
            len(constrs), expected_num_constrs, "Incorrect number of constraints added."
        )

        for t_step in self.timesteps:
            for node_name in self.nodes:
                constr_name = f"flowBal[{node_name},{t_step}]"
                current_constr = self.model.getConstrByName(constr_name)
                self.assertIsNotNone(
                    current_constr,
                    f"Constraint '{constr_name}' not found in the model.",
                )

                # 2. Check constraint sense (equality)
                self.assertEqual(
                    current_constr.Sense,
                    gp.GRB.EQUAL,
                    f"Incorrect sense for constraint '{constr_name}'. Expected equality.",
                )

                # 3. Check Right-Hand Side (RHS)
                # RHS = demand_n_t in the original formulation `LHS == demand_n_t + storage_charge`
                # Gurobi converts `LHS == C + V` to `LHS - V == C`
                expected_rhs_val = 0
                if node_name in self.demand_nodes:
                    demand_lookup_idx = t_step + (step_k - 1) * self.hours_per_step
                    expected_rhs_val = self.demand_df.loc[demand_lookup_idx, node_name]

                self.assertAlmostEqual(
                    current_constr.RHS,
                    expected_rhs_val,
                    places=6,
                    msg=f"Incorrect RHS for constraint '{constr_name}'.",
                )

                # 4. Check Left-Hand Side (LHS) terms and coefficients
                row = self.model.getRow(current_constr)
                actual_coeffs = {
                    row.getVar(i).VarName: row.getCoeff(i) for i in range(row.size())
                }

                expected_coeffs = {}

                # Generation terms (coeff: gen_efficiency)
                if node_name in self.node_generator:
                    for unit_g in self.node_generator[node_name]:
                        var = None
                        if unit_g in self.thermal_units:
                            var = self.pthermal[unit_g, t_step]
                        elif unit_g in self.hydro_units:
                            var = self.phydro[unit_g, t_step]
                        elif unit_g in self.solar_units:
                            var = self.psolar[unit_g, t_step]
                        # self.wind_units is empty, so pwind won't be added here
                        elif unit_g in self.import_units:
                            var = self.pimp[unit_g, t_step]

                        if var:  # Should always be true if data is consistent
                            expected_coeffs[var.VarName] = self.gen_efficiency

                # Net line flow terms
                if node_name in self.node_edge:
                    for x, y in self.node_edge[
                        node_name
                    ]:  # (x,y) is an edge from self.edges
                        if x == node_name:  # Edge is (node_name, y)
                            expected_coeffs[self.flow_fwd[x, y, t_step].VarName] = -1.0
                            expected_coeffs[self.flow_bwd[x, y, t_step].VarName] = (
                                self.line_efficiency
                            )
                        elif y == node_name:  # Edge is (x, node_name)
                            expected_coeffs[self.flow_fwd[x, y, t_step].VarName] = (
                                self.line_efficiency
                            )
                            expected_coeffs[self.flow_bwd[x, y, t_step].VarName] = -1.0

                # Mismatch terms
                expected_coeffs[self.pos_pmismatch[node_name, t_step].VarName] = 1.0
                expected_coeffs[self.neg_pmismatch[node_name, t_step].VarName] = -1.0

                # Storage discharge (adds to supply on LHS, coeff: 1.0)
                if node_name in self.ess_discharge_units:
                    for ess_unit in self.ess_discharge_units[node_name]:
                        expected_coeffs[self.pdis[ess_unit, t_step].VarName] = 1.0

                # Storage charge (moves from RHS to LHS, coeff: -1.0)
                if node_name in self.ess_charge_units:
                    for ess_unit in self.ess_charge_units[node_name]:
                        expected_coeffs[self.pcharge[ess_unit, t_step].VarName] = -1.0

                self.assertDictEqual(
                    actual_coeffs,
                    expected_coeffs,
                    f"Incorrect LHS coefficients for constraint '{constr_name}'.",
                )

                # Check number of terms on LHS (implicitly by assertDictEqual if keys match exactly)
                self.assertEqual(
                    len(actual_coeffs),
                    len(expected_coeffs),
                    f"Incorrect number of terms on LHS for constraint '{constr_name}'.",
                )

    def test_add_c_flow_balance_step_k_1(self):
        """Test flow balance constraints for step_k = 1."""
        self._run_test_for_step_k(step_k=1)

    def test_add_c_flow_balance_step_k_2(self):
        """Test flow balance constraints for step_k = 2."""
        self._run_test_for_step_k(step_k=2)


#########################################################################
# Tests for add_c_kirchhoff function
#########################################################################


class TestAddCKirchhoff(unittest.TestCase):
    """Test cases for the add_c_kirchhoff constraint function."""

    def _common_setup_kirchhoff(self):
        """Basic common setup for Kirchhoff tests."""
        self.model = gp.Model("test_kirchhoff")
        self.model.setParam("OutputFlag", 0)
        self.timesteps = range(1, 2)  # Single timestep: t=1
        self.step_k = 1  # Fixed step_k = 1
        self.hours_per_step = 24  # From function's internal logic

        # Flow variables will be created based on self.current_edges in specific test methods
        self.flow_fwd = gp.tupledict()
        self.flow_bwd = gp.tupledict()

    def _create_flow_vars(self, current_edges_list):
        """Helper to create flow variables for given edges."""
        for u, v in current_edges_list:
            for t in self.timesteps:
                self.flow_fwd[u, v, t] = self.model.addVar(
                    name=f"flow_fwd_{u}_{v}_{t}", lb=-gp.GRB.INFINITY
                )
                self.flow_bwd[u, v, t] = self.model.addVar(
                    name=f"flow_bwd_{u}_{v}_{t}", lb=-gp.GRB.INFINITY
                )
        self.model.update()

    def tearDown(self):
        """Clean up Gurobi model after each test."""
        if hasattr(self, "model"):  # Ensure model exists before disposing
            self.model.dispose()

    def test_kirchhoff_no_cycle(self):
        """Test KVL constraints when no cycles are defined in cycle_map."""
        self._common_setup_kirchhoff()

        current_edges = [("N1", "N2"), ("N2", "N3")]  # A simple line graph
        cycle_map = {}  # No cycles defined

        # Susceptance (B) for the edges. For t=1 (since step_k=1, timesteps=range(1,2))
        time_idx = list(self.timesteps)[0]
        susceptance_data = {
            ("N1", "N2"): {time_idx: 10.0},
            ("N2", "N3"): {time_idx: 20.0},
        }
        susceptance_df = pd.DataFrame(susceptance_data)

        self._create_flow_vars(current_edges)

        constrs = system_constr.add_c_kirchhoff(
            model=self.model,
            flow_fwd=self.flow_fwd,
            flow_bwd=self.flow_bwd,
            timesteps=self.timesteps,
            step_k=self.step_k,
            edges=current_edges,
            cycle_map=cycle_map,
            susceptance=susceptance_df,
        )
        self.model.update()

        self.assertEqual(
            len(constrs), 0, "Should be 0 KVL constraints if cycle_map is empty."
        )

    def test_kirchhoff_two_cycles(self):
        """Test KVL constraints for a graph with two defined cycles."""
        self._common_setup_kirchhoff()

        # Define edges:
        # Cycle A: N1->N2, N2->N3, N3->N1
        # Cycle B: N1->N3 (reverse of N3->N1), N3->N4, N4->N1
        current_edges = [
            ("N1", "N2"),
            ("N2", "N3"),
            ("N3", "N1"),
            ("N3", "N4"),
            ("N4", "N1"),
        ]

        # Define cycle_map for traversal
        # Node lists for cycles: [n1, n2, ..., nk] implies traversal n1->n2, ..., nk->n1
        cycle_map = {
            "CycleA": ["N1", "N2", "N3"],  # Traverses N1->N2, N2->N3, N3->N1
            "CycleB": ["N1", "N3", "N4"],  # Traverses N1->N3, N3->N4, N4->N1
        }

        # Susceptance (B) values for each defined edge
        susceptance_values = {
            ("N1", "N2"): 10.0,
            ("N2", "N3"): 12.0,
            ("N3", "N1"): 15.0,
            ("N3", "N4"): 8.0,
            ("N4", "N1"): 9.0,
        }

        time_idx = list(self.timesteps)[
            0
        ]  # Effective time index for susceptance lookup
        sus_df_data = {}
        for edge_tuple in current_edges:
            sus_df_data[edge_tuple] = {time_idx: susceptance_values[edge_tuple]}
        susceptance_df = pd.DataFrame(sus_df_data)

        self._create_flow_vars(current_edges)

        constrs = system_constr.add_c_kirchhoff(
            model=self.model,
            flow_fwd=self.flow_fwd,
            flow_bwd=self.flow_bwd,
            timesteps=self.timesteps,
            step_k=self.step_k,
            edges=current_edges,
            cycle_map=cycle_map,
            susceptance=susceptance_df,
        )
        self.model.update()

        expected_num_constraints = len(cycle_map) * len(list(self.timesteps))
        self.assertEqual(
            len(constrs),
            expected_num_constraints,
            "Incorrect number of KVL constraints added.",
        )

        t_step = list(self.timesteps)[0]  # The single timestep t=1

        # --- Check Constraint for CycleA ---
        # Traversal: N1->N2, N2->N3, N3->N1. All match defined edges.
        cname_A = f"kirchhoff[CycleA,{t_step}]"
        constr_A = self.model.getConstrByName(cname_A)
        self.assertIsNotNone(constr_A, f"Constraint {cname_A} not found.")
        self.assertEqual(constr_A.Sense, gp.GRB.EQUAL, f"Sense for {cname_A}")
        self.assertAlmostEqual(constr_A.RHS, 0.0, places=6, msg=f"RHS for {cname_A}")

        row_A = self.model.getRow(constr_A)
        actual_coeffs_A = {
            row_A.getVar(i).VarName: row_A.getCoeff(i) for i in range(row_A.size())
        }

        expected_coeffs_A = {}
        # Edge ("N1","N2"): sign=1, B=10.0, X=0.1
        expected_coeffs_A[self.flow_fwd["N1", "N2", t_step].VarName] = 1 * (1 / 10.0)
        expected_coeffs_A[self.flow_bwd["N1", "N2", t_step].VarName] = -1 * (1 / 10.0)
        # Edge ("N2","N3"): sign=1, B=12.0, X=1/12.0
        expected_coeffs_A[self.flow_fwd["N2", "N3", t_step].VarName] = 1 * (1 / 12.0)
        expected_coeffs_A[self.flow_bwd["N2", "N3", t_step].VarName] = -1 * (1 / 12.0)
        # Edge ("N3","N1"): sign=1, B=15.0, X=1/15.0
        expected_coeffs_A[self.flow_fwd["N3", "N1", t_step].VarName] = 1 * (1 / 15.0)
        expected_coeffs_A[self.flow_bwd["N3", "N1", t_step].VarName] = -1 * (1 / 15.0)

        self.assertDictEqual(
            actual_coeffs_A, expected_coeffs_A, f"Coefficients mismatch for {cname_A}"
        )

        # --- Check Constraint for CycleB ---
        # Traversal: N1->N3, N3->N4, N4->N1
        cname_B = f"kirchhoff[CycleB,{t_step}]"
        constr_B = self.model.getConstrByName(cname_B)
        self.assertIsNotNone(constr_B, f"Constraint {cname_B} not found.")
        self.assertEqual(constr_B.Sense, gp.GRB.EQUAL, f"Sense for {cname_B}")
        self.assertAlmostEqual(constr_B.RHS, 0.0, places=6, msg=f"RHS for {cname_B}")

        row_B = self.model.getRow(constr_B)
        actual_coeffs_B = {
            row_B.getVar(i).VarName: row_B.getCoeff(i) for i in range(row_B.size())
        }

        expected_coeffs_B = {}
        # Traversed N1->N3: Original edge is ("N3","N1") (B=15.0), so sign=-1. X=1/15.0
        # Term: -1 * (1/15.0) * (flow_fwd["N3","N1"] - flow_bwd["N3","N1"])
        expected_coeffs_B[self.flow_fwd["N3", "N1", t_step].VarName] = -1 * (1 / 15.0)
        expected_coeffs_B[self.flow_bwd["N3", "N1", t_step].VarName] = 1 * (1 / 15.0)
        # Traversed N3->N4: Original edge is ("N3","N4") (B=8.0), sign=1. X=1/8.0
        expected_coeffs_B[self.flow_fwd["N3", "N4", t_step].VarName] = 1 * (1 / 8.0)
        expected_coeffs_B[self.flow_bwd["N3", "N4", t_step].VarName] = -1 * (1 / 8.0)
        # Traversed N4->N1: Original edge is ("N4","N1") (B=9.0), sign=1. X=1/9.0
        expected_coeffs_B[self.flow_fwd["N4", "N1", t_step].VarName] = 1 * (1 / 9.0)
        expected_coeffs_B[self.flow_bwd["N4", "N1", t_step].VarName] = -1 * (1 / 9.0)

        self.assertDictEqual(
            actual_coeffs_B, expected_coeffs_B, f"Coefficients mismatch for {cname_B}"
        )


#########################################################################
# Tests for adding thermal curtailment and ESS constraints
#########################################################################


HOURS_PER_STEP_ASSUMED = 24  # Standard assumption for hourly indexing


def add_c_thermal_curtail_ess_impl(
    model: gp.Model,
    pthermal: gp.tupledict,
    pthermal_curtail: gp.tupledict,
    pcharge: gp.tupledict,
    timesteps: range,
    step_k: int,
    thermal_must_take_units: list,
    thermal_derated_capacity: pd.DataFrame,
    ess_attached: dict,
) -> gp.tupledict:
    hours_per_step = HOURS_PER_STEP_ASSUMED
    constraints = gp.tupledict()
    for unit in thermal_must_take_units:
        has_storage = (
            unit in ess_attached and ess_attached[unit]
        )  # also check if list is not empty
        for t in timesteps:
            pcharge_unit_t = gp.LinExpr()  # Use LinExpr for summing variables
            if has_storage:
                for storage_unit in ess_attached[unit]:
                    pcharge_unit_t.add(pcharge[storage_unit, t])
            cname = f"thermal_curtail[{unit},{t}]"
            constraints[cname] = model.addConstr(
                (
                    pthermal[unit, t] + pthermal_curtail[unit, t] + pcharge_unit_t
                    == thermal_derated_capacity.loc[
                        t + (step_k - 1) * hours_per_step, unit
                    ]
                ),
                name=cname,
            )
    return constraints


def add_c_unit_curtail_ess_impl(
    model: gp.Model,
    pdispatch: gp.tupledict,
    pcurtail: gp.tupledict,
    pcharge: gp.tupledict,
    unit_type: str,
    timesteps: range,
    step_k: int,
    units: list,
    capacity_df: pd.DataFrame,
    ess_attached: dict[str, list[str]],
) -> gp.tupledict:
    constraints = gp.tupledict()
    for unit in units:
        has_storage = unit in ess_attached and ess_attached[unit]
        for t in timesteps:
            pcharge_unit_t = gp.LinExpr()
            if has_storage:
                for storage_unit in ess_attached[unit]:
                    pcharge_unit_t.add(pcharge[storage_unit, t])
            cname = f"{unit_type}_curtail_ess[{unit},{t}]"
            # Assuming get_capacity_value logic based on context:
            rhs_capacity = capacity_df.loc[
                t + (step_k - 1) * HOURS_PER_STEP_ASSUMED, unit
            ]
            constraints[cname] = model.addConstr(
                (
                    pdispatch[unit, t] + pcurtail[unit, t] + pcharge_unit_t
                    == rhs_capacity
                ),
                name=cname,
            )
    return constraints


def add_c_unit_curtail_ess_daily_impl(
    model: gp.Model,
    pdispatch: gp.tupledict,
    pcurtail: gp.tupledict,
    pcharge: gp.tupledict,
    unit_type: str,
    sim_horizon: int,
    step_k: int,
    units: list,
    capacity_df: pd.DataFrame,
    ess_attached: dict[str, list[str]],
) -> gp.tupledict:
    constraints = gp.tupledict()
    max_day = sim_horizon // 24
    if (
        max_day == 0 and sim_horizon > 0
    ):  # handle sim_horizon < 24 hours if it means no full days
        return constraints  # Or raise error, depending on desired behavior for sub-daily sim_horizon

    for unit in units:
        has_storage = unit in ess_attached and ess_attached[unit]
        # The loop for 'day' should iterate over the number of relevant days based on sim_horizon and step_k
        # The original 'day' loop: range(step_k, step_k + max_day) is correct for capacity_df indexing.
        for day_idx_for_capacity in range(step_k, step_k + max_day):
            # Calculate hourly timesteps corresponding to this day_idx_for_capacity
            # 'current_day_offset' is the 1-based day number within the optimization window defined by step_k & max_day
            current_day_offset = day_idx_for_capacity - step_k + 1

            # Timesteps are typically 1-indexed for the overall simulation horizon
            start_hour_of_day = 1 + (current_day_offset - 1) * 24
            end_hour_of_day = current_day_offset * 24
            timesteps_in_day = range(start_hour_of_day, end_hour_of_day + 1)

            sum_pdispatch_pcurtail_day = gp.quicksum(
                pdispatch[unit, t_hour] + pcurtail[unit, t_hour]
                for t_hour in timesteps_in_day
            )

            pcharge_unit_day_sum = gp.LinExpr()
            if has_storage:
                for storage_unit in ess_attached[unit]:
                    pcharge_unit_day_sum.add(
                        gp.quicksum(
                            pcharge[storage_unit, t_hour] for t_hour in timesteps_in_day
                        )
                    )

            cname = f"{unit_type}_curtail_ess[{unit},{day_idx_for_capacity}]"
            constraints[cname] = model.addConstr(
                (
                    sum_pdispatch_pcurtail_day + pcharge_unit_day_sum
                    == capacity_df.loc[day_idx_for_capacity, unit]
                ),
                name=cname,
            )
    return constraints


# system_constr = DummySystemConstrModule()
# system_constr.add_c_thermal_curtail_ess = add_c_thermal_curtail_ess_impl
# system_constr.add_c_unit_curtail_ess = add_c_unit_curtail_ess_impl
# system_constr.add_c_unit_curtail_ess_daily = add_c_unit_curtail_ess_daily_impl

# --- Unittest Classes ---


class TestAddCThermalCurtailEss(unittest.TestCase):
    """Tests for add_c_thermal_curtail_ess function."""

    def setUp(self):
        self.model = gp.Model("test_thermal_curtail_ess")
        self.model.setParam("OutputFlag", 0)
        self.timesteps = range(1, 3)  # t=1, 2
        self.hours_per_step = HOURS_PER_STEP_ASSUMED

        self.thermal_units_all = ["TH1", "TH2", "TH3_no_ess", "TH4_not_must_take"]
        self.thermal_must_take_units = ["TH1", "TH2", "TH3_no_ess"]
        self.ess_units = ["ESS_A", "ESS_B", "ESS_C"]
        self.ess_attached = {
            "TH1": [self.ess_units[0]],  # TH1 attached to ESS_A
            "TH2": [
                self.ess_units[1],
                self.ess_units[2],
            ],  # TH2 attached to ESS_B, ESS_C
            # TH3_no_ess is must-take but not in ess_attached
        }

        self.pthermal = self.model.addVars(
            self.thermal_units_all, self.timesteps, name="pthermal"
        )
        self.pthermal_curtail = self.model.addVars(
            self.thermal_units_all, self.timesteps, name="pthermal_curtail"
        )
        self.pcharge = self.model.addVars(
            self.ess_units, self.timesteps, name="pcharge"
        )
        self.model.update()

    def tearDown(self):
        self.model.dispose()

    def _run_test_step_k(self, step_k):
        # Prepare thermal_derated_capacity DataFrame
        cap_data = {}
        # Time indices needed for capacity_df based on step_k and timesteps
        abs_time_indices = [
            t + (step_k - 1) * self.hours_per_step for t in self.timesteps
        ]

        for unit in self.thermal_must_take_units:
            cap_data[unit] = {
                abs_idx: (100 + i * 10 + self.thermal_must_take_units.index(unit) * 5)
                for i, abs_idx in enumerate(abs_time_indices)
            }
        thermal_derated_capacity_df = pd.DataFrame(cap_data, index=abs_time_indices)

        constrs = system_constr.add_c_thermal_curtail_ess(
            model=self.model,
            pthermal=self.pthermal,
            pthermal_curtail=self.pthermal_curtail,
            pcharge=self.pcharge,
            timesteps=self.timesteps,
            step_k=step_k,
            thermal_must_take_units=self.thermal_must_take_units,
            thermal_derated_capacity=thermal_derated_capacity_df,
            ess_attached=self.ess_attached,
        )
        self.model.update()

        self.assertEqual(
            len(constrs), len(self.thermal_must_take_units) * len(list(self.timesteps))
        )

        for unit in self.thermal_must_take_units:
            for t in self.timesteps:
                cname = f"thermal_curtail[{unit},{t}]"
                constr = self.model.getConstrByName(cname)
                self.assertIsNotNone(constr, f"Constraint {cname} not found.")
                self.assertEqual(constr.Sense, gp.GRB.EQUAL)

                expected_rhs = thermal_derated_capacity_df.loc[
                    t + (step_k - 1) * self.hours_per_step, unit
                ]
                self.assertAlmostEqual(constr.RHS, expected_rhs, places=6)

                row = self.model.getRow(constr)
                actual_coeffs = {
                    row.getVar(i).VarName: row.getCoeff(i) for i in range(row.size())
                }

                expected_coeffs = {
                    self.pthermal[unit, t].VarName: 1.0,
                    self.pthermal_curtail[unit, t].VarName: 1.0,
                }
                if unit in self.ess_attached:
                    for ess_unit in self.ess_attached[unit]:
                        expected_coeffs[self.pcharge[ess_unit, t].VarName] = 1.0

                self.assertDictEqual(
                    actual_coeffs, expected_coeffs, f"Coeffs mismatch for {cname}"
                )

    def test_thermal_curtail_ess_step_k_1(self):
        self._run_test_step_k(step_k=1)

    def test_thermal_curtail_ess_step_k_2(self):
        self._run_test_step_k(step_k=2)


class TestAddCUnitCurtailEss(unittest.TestCase):
    """Tests for add_c_unit_curtail_ess function."""

    def setUp(self):
        self.model = gp.Model("test_unit_curtail_ess")
        self.model.setParam("OutputFlag", 0)
        self.timesteps = range(1, 3)  # t=1, 2
        self.hours_per_step = HOURS_PER_STEP_ASSUMED
        self.unit_type = "solar"

        self.solar_units_all = [
            "S1",
            "S2",
            "S3_no_ess",
            "S4_other_type",
        ]  # All solar units in the system
        self.units_to_constrain = [
            "S1",
            "S2",
            "S3_no_ess",
        ]  # Units to apply constraint for
        self.ess_units = ["ESS_S1A", "ESS_S2A", "ESS_S2B"]
        self.ess_attached = {
            "S1": [self.ess_units[0]],
            "S2": [self.ess_units[1], self.ess_units[2]],
        }

        self.pdispatch = self.model.addVars(
            self.solar_units_all, self.timesteps, name="pdispatch_solar"
        )
        self.pcurtail = self.model.addVars(
            self.solar_units_all, self.timesteps, name="pcurtail_solar"
        )
        self.pcharge = self.model.addVars(
            self.ess_units, self.timesteps, name="pcharge_ess_solar"
        )
        self.model.update()

    def tearDown(self):
        self.model.dispose()

    def _run_test_step_k(self, step_k):
        cap_data = {}
        abs_time_indices = [
            t + (step_k - 1) * self.hours_per_step for t in self.timesteps
        ]
        for (
            unit
        ) in (
            self.units_to_constrain
        ):  # Capacity only needed for units constraint is applied to
            cap_data[unit] = {
                abs_idx: (80 + i * 5 + self.units_to_constrain.index(unit) * 3)
                for i, abs_idx in enumerate(abs_time_indices)
            }
        capacity_df = pd.DataFrame(cap_data, index=abs_time_indices)

        constrs = system_constr.add_c_unit_curtail_ess(
            model=self.model,
            pdispatch=self.pdispatch,
            pcurtail=self.pcurtail,
            pcharge=self.pcharge,
            unit_type=self.unit_type,
            timesteps=self.timesteps,
            step_k=step_k,
            units=self.units_to_constrain,
            capacity_df=capacity_df,
            ess_attached=self.ess_attached,
        )
        self.model.update()

        self.assertEqual(
            len(constrs), len(self.units_to_constrain) * len(list(self.timesteps))
        )

        for unit in self.units_to_constrain:
            for t in self.timesteps:
                cname = f"{self.unit_type}_curtail_ess[{unit},{t}]"
                constr = self.model.getConstrByName(cname)
                self.assertIsNotNone(constr, f"Constraint {cname} not found.")
                self.assertEqual(constr.Sense, gp.GRB.EQUAL)

                expected_rhs = capacity_df.loc[
                    t + (step_k - 1) * self.hours_per_step, unit
                ]
                self.assertAlmostEqual(constr.RHS, expected_rhs, places=6)

                row = self.model.getRow(constr)
                actual_coeffs = {
                    row.getVar(i).VarName: row.getCoeff(i) for i in range(row.size())
                }

                expected_coeffs = {
                    self.pdispatch[unit, t].VarName: 1.0,
                    self.pcurtail[unit, t].VarName: 1.0,
                }
                if unit in self.ess_attached:
                    for ess_unit in self.ess_attached[unit]:
                        expected_coeffs[self.pcharge[ess_unit, t].VarName] = 1.0

                self.assertDictEqual(
                    actual_coeffs, expected_coeffs, f"Coeffs mismatch for {cname}"
                )

    def test_unit_curtail_ess_step_k_1(self):
        self._run_test_step_k(step_k=1)

    def test_unit_curtail_ess_step_k_2(self):
        self._run_test_step_k(step_k=2)


class TestAddCUnitCurtailEssDaily(unittest.TestCase):
    """Tests for add_c_unit_curtail_ess_daily function."""

    def setUp(self):
        self.model = gp.Model("test_unit_curtail_ess_daily")
        self.model.setParam("OutputFlag", 0)
        self.unit_type = "wind"
        self.sim_horizon = 48  # 2 days
        self.hourly_timesteps = range(1, self.sim_horizon + 1)

        self.wind_units_all = ["W1", "W2", "W3_no_ess"]  # All wind units
        self.units_to_constrain = [
            "W1",
            "W2",
            "W3_no_ess",
        ]  # Units to apply constraint for
        self.ess_units = ["ESS_W1A", "ESS_W2A"]
        self.ess_attached = {
            "W1": [self.ess_units[0]],
            "W2": [self.ess_units[1]],
        }

        self.pdispatch = self.model.addVars(
            self.wind_units_all, self.hourly_timesteps, name="pdispatch_wind"
        )
        self.pcurtail = self.model.addVars(
            self.wind_units_all, self.hourly_timesteps, name="pcurtail_wind"
        )
        self.pcharge = self.model.addVars(
            self.ess_units, self.hourly_timesteps, name="pcharge_ess_wind"
        )
        self.model.update()

    def tearDown(self):
        self.model.dispose()

    def _run_test_step_k(self, step_k_day_start_idx):
        # Daily capacity data
        num_total_days_in_sim = self.sim_horizon // 24
        # Days for which capacity data is needed, matching the 'day' loop in the function
        # The 'day' loop in func: range(step_k_day_start_idx, step_k_day_start_idx + num_total_days_in_sim)
        capacity_day_indices = range(
            step_k_day_start_idx, step_k_day_start_idx + num_total_days_in_sim
        )

        daily_cap_data = {}
        for unit in self.units_to_constrain:
            daily_cap_data[unit] = {
                day_idx: (
                    2000
                    + (day_idx - step_k_day_start_idx) * 100
                    + self.units_to_constrain.index(unit) * 50
                )
                for day_idx in capacity_day_indices
            }
        daily_capacity_df = pd.DataFrame(daily_cap_data, index=capacity_day_indices)

        constrs = system_constr.add_c_unit_curtail_ess_daily(
            model=self.model,
            pdispatch=self.pdispatch,
            pcurtail=self.pcurtail,
            pcharge=self.pcharge,
            unit_type=self.unit_type,
            sim_horizon=self.sim_horizon,
            step_k=step_k_day_start_idx,  # This is the starting day index
            units=self.units_to_constrain,
            capacity_df=daily_capacity_df,
            ess_attached=self.ess_attached,
        )
        self.model.update()

        # Number of days the constraint will actually be added for
        max_days_constrained = self.sim_horizon // 24
        self.assertEqual(
            len(constrs), len(self.units_to_constrain) * max_days_constrained
        )

        for unit in self.units_to_constrain:
            # day_loop_idx is the 'day' in range(step_k, step_k + max_day) from the function
            for i in range(max_days_constrained):
                day_loop_idx = step_k_day_start_idx + i

                cname = f"{self.unit_type}_curtail_ess[{unit},{day_loop_idx}]"
                constr = self.model.getConstrByName(cname)
                self.assertIsNotNone(constr, f"Constraint {cname} not found.")
                self.assertEqual(constr.Sense, gp.GRB.EQUAL)

                expected_rhs = daily_capacity_df.loc[day_loop_idx, unit]
                self.assertAlmostEqual(constr.RHS, expected_rhs, places=6)

                row = self.model.getRow(constr)
                actual_coeffs = {
                    row.getVar(i).VarName: row.getCoeff(i) for i in range(row.size())
                }
                expected_coeffs = {}

                current_day_offset = day_loop_idx - step_k_day_start_idx + 1
                start_hour = 1 + (current_day_offset - 1) * 24
                end_hour = current_day_offset * 24
                timesteps_this_day = range(start_hour, end_hour + 1)

                for t_hour in timesteps_this_day:
                    expected_coeffs[self.pdispatch[unit, t_hour].VarName] = 1.0
                    expected_coeffs[self.pcurtail[unit, t_hour].VarName] = 1.0
                    if unit in self.ess_attached:
                        for ess_unit in self.ess_attached[unit]:
                            expected_coeffs[self.pcharge[ess_unit, t_hour].VarName] = (
                                1.0
                            )

                self.assertDictEqual(
                    actual_coeffs, expected_coeffs, f"Coeffs mismatch for {cname}"
                )

    def test_daily_curtail_ess_step_k_1(self):
        self._run_test_step_k(step_k_day_start_idx=1)

    def test_daily_curtail_ess_step_k_3_sim_5_days(self):
        # Test with a later step_k (e.g., day 3 of a 5-day simulation)
        self.sim_horizon = 5 * 24  # 5 days total simulation
        self.hourly_timesteps = range(1, self.sim_horizon + 1)
        # Re-setup variables for the new sim_horizon
        self.pdispatch = self.model.addVars(
            self.wind_units_all, self.hourly_timesteps, name="pdispatch_wind_5d"
        )
        self.pcurtail = self.model.addVars(
            self.wind_units_all, self.hourly_timesteps, name="pcurtail_wind_5d"
        )
        self.pcharge = self.model.addVars(
            self.ess_units, self.hourly_timesteps, name="pcharge_ess_wind_5d"
        )
        self.model.update()
        self._run_test_step_k(step_k_day_start_idx=3)


if __name__ == "__main__":
    unittest.main()
