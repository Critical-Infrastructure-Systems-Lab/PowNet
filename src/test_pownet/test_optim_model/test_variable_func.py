"""test_variable_func.py"""

import unittest
from unittest.mock import MagicMock, patch, call
import pandas as pd

from pownet.optim_model import variable_func


class TestVariableFunctions(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Set up class-level resources or patches before any tests in the class run."""
        variable_func.VAR_PREFIX_THERMAL_GENERATION = "thermal_generation"

    def setUp(self):
        """Set up common test data and mocks."""

        self.VAR_PREFIX_THERMAL_GENERATION = "thermal_generation"

        self.timesteps = range(
            3
        )  # Global timestep as per user request (implicitly via usage)
        self.units = ["gen_A", "gen_B"]
        self.edges = [("node1", "node2"), ("node2", "node3")]
        self.step_k = 1  # Default step_k, can be overridden in specific tests

        # Mock Gurobi model
        self.mock_model = MagicMock()
        # This mock will be returned by model.addVars
        self.mock_vars_tupledict = MagicMock()
        self.mock_model.addVars.return_value = self.mock_vars_tupledict

        # Dummy capacity DataFrame for functions where its internal structure
        # isn't directly tested by the function itself but passed to a mocked helper.
        self.dummy_capacity_df = pd.DataFrame({"dummy_col": [1, 2, 3]})

        # More structured capacity DataFrame for update_flow_vars
        # Index needs to cover t + (step_k - 1) * 24
        # For step_k=1, t=0,1,2 -> index 0,1,2
        # For step_k=2, t=0,1,2 -> index 24,25,26
        idx = pd.RangeIndex(start=0, stop=50, step=1)  # Sufficient for a few steps
        data_for_flow_df = {
            self.edges[0]: [100 + i for i in range(50)],
            self.edges[1]: [200 + i for i in range(50)],
        }
        self.flow_capacity_df = pd.DataFrame(data_for_flow_df, index=idx)

    @patch("pownet.optim_model.variable_func.GRB")
    @patch("pownet.optim_model.variable_func.get_capacity_value")
    def test_add_var_with_variable_ub(self, mock_get_capacity_value, mock_grb_module):
        """Test the add_var_with_variable_ub function."""
        var_name = "test_var"
        step_k_test = 2

        mock_grb_module.CONTINUOUS = "MOCK_GRB_CONTINUOUS_TYPE"

        # Define a side effect for mock_get_capacity_value to simulate different capacities
        def capacity_side_effect(t, unit, sk, df):
            # sk is step_k, df is capacity_df
            # Simple unique value based on inputs for verification
            if unit == self.units[0]:
                return 100 + t + sk
            elif unit == self.units[1]:
                return 200 + t + sk
            return 0

        mock_get_capacity_value.side_effect = capacity_side_effect

        # Expected upper bounds dictionary
        expected_ub_dict = {}
        for t_val in self.timesteps:
            for unit_val in self.units:
                expected_ub_dict[(unit_val, t_val)] = capacity_side_effect(
                    t_val, unit_val, step_k_test, self.dummy_capacity_df
                )

        # Call the function
        created_vars = variable_func.add_var_with_variable_ub(
            model=self.mock_model,
            varname=var_name,
            timesteps=self.timesteps,
            step_k=step_k_test,
            units=self.units,
            capacity_df=self.dummy_capacity_df,
        )

        # Assert model.addVars was called correctly
        self.mock_model.addVars.assert_called_once_with(
            self.units,
            self.timesteps,
            lb=0,
            ub=expected_ub_dict,
            vtype="MOCK_GRB_CONTINUOUS_TYPE",  # Check if the mocked GRB type is used
            name=var_name,
        )

        # Assert that the function returns what model.addVars returned
        self.assertEqual(created_vars, self.mock_vars_tupledict)

        # Verify calls to get_capacity_value
        expected_calls_to_get_capacity = []
        for t_val in self.timesteps:
            for unit_val in self.units:
                expected_calls_to_get_capacity.append(
                    call(t_val, unit_val, step_k_test, self.dummy_capacity_df)
                )
        mock_get_capacity_value.assert_has_calls(
            expected_calls_to_get_capacity, any_order=True
        )
        self.assertEqual(
            mock_get_capacity_value.call_count, len(self.units) * len(self.timesteps)
        )

    @patch("pownet.optim_model.variable_func.get_capacity_value")
    @patch("pownet.optim_model.variable_func.get_unit_hour_from_varname")
    def test_update_var_with_variable_ub(
        self, mock_get_unit_hour_from_varname, mock_get_capacity_value
    ):
        """Test the update_var_with_variable_ub function."""
        step_k_test = 1

        # Create mock Gurobi variables
        mock_gvar1 = MagicMock()
        mock_gvar1.VarName = (
            f"{variable_func.VAR_PREFIX_THERMAL_GENERATION}_{self.units[0]}[0]"
        )
        mock_gvar1.ub = 0  # Initial ub

        mock_gvar2 = MagicMock()
        mock_gvar2.VarName = (
            f"{variable_func.VAR_PREFIX_THERMAL_GENERATION}_{self.units[1]}[1]"
        )
        mock_gvar2.ub = 0  # Initial ub

        # Simulate a gp.tupledict by using a dictionary of these mocks
        # The function iterates over .values()
        mock_variables_dict = {
            (self.units[0], 0): mock_gvar1,
            (self.units[1], 1): mock_gvar2,
        }

        # Configure side effect for get_unit_hour_from_varname
        def unit_hour_side_effect(var_name):
            if var_name == mock_gvar1.VarName:
                return self.units[0], 0
            elif var_name == mock_gvar2.VarName:
                return self.units[1], 1
            return None, None  # Should not happen with controlled inputs

        mock_get_unit_hour_from_varname.side_effect = unit_hour_side_effect

        # Configure side effect for get_capacity_value
        # Capacity depends on unit, t, and step_k
        expected_capacity_gvar1 = 150
        expected_capacity_gvar2 = 250

        def capacity_side_effect(t, unit, sk, df):
            self.assertEqual(sk, step_k_test)  # Check step_k is passed correctly
            self.assertIs(df, self.dummy_capacity_df)  # Check df is passed correctly
            if unit == self.units[0] and t == 0:
                return expected_capacity_gvar1
            elif unit == self.units[1] and t == 1:
                return expected_capacity_gvar2
            return 0  # Default, should not be hit with specific var names

        mock_get_capacity_value.side_effect = capacity_side_effect

        # Call the function
        # Pass the .values() if the function expects an iterable of Gurobi variables
        # The type hint is gp.tupledict, so we pass the dict itself.
        variable_func.update_var_with_variable_ub(
            variables=mock_variables_dict,
            step_k=step_k_test,
            capacity_df=self.dummy_capacity_df,
        )

        # Assertions
        # Check get_unit_hour_from_varname calls
        mock_get_unit_hour_from_varname.assert_any_call(mock_gvar1.VarName)
        mock_get_unit_hour_from_varname.assert_any_call(mock_gvar2.VarName)
        self.assertEqual(mock_get_unit_hour_from_varname.call_count, 2)

        # Check get_capacity_value calls
        mock_get_capacity_value.assert_any_call(
            0, self.units[0], step_k_test, self.dummy_capacity_df
        )
        mock_get_capacity_value.assert_any_call(
            1, self.units[1], step_k_test, self.dummy_capacity_df
        )
        self.assertEqual(mock_get_capacity_value.call_count, 2)

        # Check if variable upper bounds were updated
        self.assertEqual(mock_gvar1.ub, expected_capacity_gvar1)
        self.assertEqual(mock_gvar2.ub, expected_capacity_gvar2)

    @patch("pownet.optim_model.variable_func.get_edge_hour_from_varname")
    def test_update_flow_vars(self, mock_get_edge_hour_from_varname):
        """Test the update_flow_vars function."""
        step_k_test = 2  # Using a different step_k to test the time indexing
        line_capacity_factor = 0.9
        hours_per_step = 24  # As defined in the source function

        # Create mock Gurobi flow variables
        mock_flow_var1 = MagicMock()
        # Example VarName format, assuming some prefix like "flow_"
        mock_flow_var1.VarName = f"flow_{self.edges[0][0]}_{self.edges[0][1]}[0]"
        mock_flow_var1.ub = 0  # Initial ub

        mock_flow_var2 = MagicMock()
        mock_flow_var2.VarName = (
            f"flow_{self.edges[1][0]}_{self.edges[1][1]}[2]"  # t=2 for this var
        )
        mock_flow_var2.ub = 0

        mock_flow_variables_dict = {
            (self.edges[0], 0): mock_flow_var1,
            (self.edges[1], 2): mock_flow_var2,
        }

        # Configure side effect for get_edge_hour_from_varname
        def edge_hour_side_effect(var_name):
            if var_name == mock_flow_var1.VarName:
                return self.edges[0], 0  # (edge_tuple, time_in_step)
            elif var_name == mock_flow_var2.VarName:
                return self.edges[1], 2
            return None, None

        mock_get_edge_hour_from_varname.side_effect = edge_hour_side_effect

        # Call the function
        variable_func.update_flow_vars(
            flow_variables=mock_flow_variables_dict,  # Pass dict, function iterates .values()
            step_k=step_k_test,
            capacity_df=self.flow_capacity_df,
            line_capacity_factor=line_capacity_factor,
        )

        # Assertions
        # Check get_edge_hour_from_varname calls
        mock_get_edge_hour_from_varname.assert_any_call(mock_flow_var1.VarName)
        mock_get_edge_hour_from_varname.assert_any_call(mock_flow_var2.VarName)
        self.assertEqual(mock_get_edge_hour_from_varname.call_count, 2)

        # Calculate expected capacities and UBs
        # For flow_var1: edge=self.edges[0], t=0
        time_idx1 = 0 + (step_k_test - 1) * hours_per_step  # 0 + (2-1)*24 = 24
        expected_capacity1 = self.flow_capacity_df.loc[time_idx1, self.edges[0]]
        expected_ub1 = expected_capacity1 * line_capacity_factor

        # For flow_var2: edge=self.edges[1], t=2
        time_idx2 = 2 + (step_k_test - 1) * hours_per_step  # 2 + (2-1)*24 = 26
        expected_capacity2 = self.flow_capacity_df.loc[time_idx2, self.edges[1]]
        expected_ub2 = expected_capacity2 * line_capacity_factor

        # Check if flow variable upper bounds were updated
        self.assertEqual(mock_flow_var1.ub, expected_ub1)
        self.assertEqual(mock_flow_var2.ub, expected_ub2)


# This allows running the tests directly from the script
if __name__ == "__main__":
    unittest.main()
