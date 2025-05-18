"""test_variable_func.py: Unit tests for variable_func.py."""

import unittest
from unittest.mock import MagicMock, patch, call
import pandas as pd

# Assuming variable_func is in pownet.optim_model directory
# Adjust the import path if your directory structure is different.
# For example, if pownet is in your PYTHONPATH:
from pownet.optim_model import variable_func

# If variable_func.py is in the same directory as the test for local testing,
# you might use:
# import variable_func


class TestVariableFunctions(unittest.TestCase):

    # Removed setUpClass as VAR_PREFIX_THERMAL_GENERATION is no longer used
    # in variable_func.py

    def setUp(self):
        """Set up common test data and mocks."""

        self.timesteps = range(3)
        self.units = ["gen_A", "gen_B"]
        self.edges = [("node1", "node2"), ("node2", "node3")]
        self.step_k = 1  # Default step_k, can be overridden

        # Mock Gurobi model
        self.mock_model = MagicMock()
        # This mock will be returned by model.addVars
        self.mock_vars_tupledict = MagicMock()
        self.mock_model.addVars.return_value = self.mock_vars_tupledict

        # Dummy capacity DataFrame for functions where its internal structure
        # isn't directly tested by the function itself but passed to a mocked helper.
        self.dummy_capacity_df = pd.DataFrame({"dummy_col": [1, 2, 3]})

        # More structured capacity DataFrame for update_flow_vars
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

        # Mock the GRB constant
        mock_grb_module.CONTINUOUS = "MOCK_GRB_CONTINUOUS_TYPE"

        # Define a side effect for mock_get_capacity_value
        def capacity_side_effect(t, unit, sk, df):
            self.assertIs(df, self.dummy_capacity_df)  # Ensure correct df is passed
            if unit == self.units[0]:
                return 100 + t + sk
            elif unit == self.units[1]:
                return 200 + t + sk
            return 0

        mock_get_capacity_value.side_effect = capacity_side_effect

        # Expected upper bounds dictionary based on the side effect
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
            vtype="MOCK_GRB_CONTINUOUS_TYPE",
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
    def test_update_var_with_variable_ub(self, mock_get_capacity_value):
        """Test the update_var_with_variable_ub function."""
        step_k_test = 1

        # Create mock Gurobi variables (VarName is not used by the new function logic)
        mock_gvar1 = MagicMock()
        mock_gvar1.ub = 0  # Initial ub

        mock_gvar2 = MagicMock()
        mock_gvar2.ub = 0  # Initial ub

        mock_gvar3 = MagicMock()  # For a different timestep
        mock_gvar3.ub = 0

        # Simulate a gp.tupledict by using a Python dictionary of these mocks
        # Keys are (unit, t) as expected by the function's iteration
        mock_variables_dict = {
            (self.units[0], 0): mock_gvar1,  # (unit, t)
            (self.units[1], 1): mock_gvar2,
            (self.units[0], 2): mock_gvar3,
        }

        # Configure side effect for get_capacity_value
        expected_capacity_gvar1 = 150
        expected_capacity_gvar2 = 250
        expected_capacity_gvar3 = 175

        def capacity_side_effect(t_arg, unit_arg, sk_arg, df_arg):
            self.assertEqual(sk_arg, step_k_test)
            self.assertIs(df_arg, self.dummy_capacity_df)
            if unit_arg == self.units[0] and t_arg == 0:
                return expected_capacity_gvar1
            elif unit_arg == self.units[1] and t_arg == 1:
                return expected_capacity_gvar2
            elif unit_arg == self.units[0] and t_arg == 2:
                return expected_capacity_gvar3
            return 0  # Default, should not be hit

        mock_get_capacity_value.side_effect = capacity_side_effect

        # Call the function
        variable_func.update_var_with_variable_ub(
            variables=mock_variables_dict,
            step_k=step_k_test,
            capacity_df=self.dummy_capacity_df,
        )

        # Assertions
        # Check get_capacity_value calls
        # The calls are made based on the keys of mock_variables_dict
        expected_calls = [
            call(0, self.units[0], step_k_test, self.dummy_capacity_df),
            call(1, self.units[1], step_k_test, self.dummy_capacity_df),
            call(2, self.units[0], step_k_test, self.dummy_capacity_df),
        ]
        mock_get_capacity_value.assert_has_calls(expected_calls, any_order=True)
        self.assertEqual(mock_get_capacity_value.call_count, len(mock_variables_dict))

        # Check if variable upper bounds were updated
        self.assertEqual(mock_gvar1.ub, expected_capacity_gvar1)
        self.assertEqual(mock_gvar2.ub, expected_capacity_gvar2)
        self.assertEqual(mock_gvar3.ub, expected_capacity_gvar3)

    def test_update_flow_vars(
        self,
    ):  # No external calls to mock within update_flow_vars directly
        """Test the update_flow_vars function."""
        step_k_test = 2
        line_capacity_factor = 0.9
        hours_per_step = 24  # As defined in the source function

        # Create mock Gurobi flow variables
        mock_flow_var1 = MagicMock()
        mock_flow_var1.ub = 0  # Initial ub

        mock_flow_var2 = MagicMock()
        mock_flow_var2.ub = 0

        # Keys are (node1, node2, t) as expected by the function's iteration
        mock_flow_variables_dict = {
            (
                self.edges[0][0],
                self.edges[0][1],
                0,
            ): mock_flow_var1,  # ("node1", "node2", 0)
            (
                self.edges[1][0],
                self.edges[1][1],
                2,
            ): mock_flow_var2,  # ("node2", "node3", 2)
        }

        # Call the function
        variable_func.update_flow_vars(
            flow_variables=mock_flow_variables_dict,
            step_k=step_k_test,
            capacity_df=self.flow_capacity_df,
            line_capacity_factor=line_capacity_factor,
        )

        # Calculate expected capacities and UBs
        # For flow_var1: edge=self.edges[0] ("node1", "node2"), t=0
        key1_node1, key1_node2, key1_t = self.edges[0][0], self.edges[0][1], 0
        edge1 = (key1_node1, key1_node2)
        time_idx1 = key1_t + (step_k_test - 1) * hours_per_step  # 0 + (2-1)*24 = 24
        expected_capacity1 = self.flow_capacity_df.loc[time_idx1, edge1]
        expected_ub1 = expected_capacity1 * line_capacity_factor

        # For flow_var2: edge=self.edges[1] ("node2", "node3"), t=2
        key2_node1, key2_node2, key2_t = self.edges[1][0], self.edges[1][1], 2
        edge2 = (key2_node1, key2_node2)
        time_idx2 = key2_t + (step_k_test - 1) * hours_per_step  # 2 + (2-1)*24 = 26
        expected_capacity2 = self.flow_capacity_df.loc[time_idx2, edge2]
        expected_ub2 = expected_capacity2 * line_capacity_factor

        # Check if flow variable upper bounds were updated
        self.assertEqual(mock_flow_var1.ub, expected_ub1)
        self.assertEqual(mock_flow_var2.ub, expected_ub2)


if __name__ == "__main__":
    unittest.main()
