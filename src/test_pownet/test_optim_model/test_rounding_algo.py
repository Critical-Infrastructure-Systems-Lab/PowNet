import unittest
from unittest.mock import MagicMock, patch, call
import numpy as np

# Import the module to be tested
from pownet.optim_model import rounding_algo


# Helper to create mock Gurobi variables
def create_mock_gurobi_var(val, name="var", lb=0.0, ub=1.0):
    """Creates a MagicMock simulating a Gurobi variable."""
    var = MagicMock()
    var.X = val
    var.varName = name  # Corrected: varname to match usage in rounding_algo.py
    var.lb = lb
    var.ub = ub
    return var


class TestRoundingAlgorithm(unittest.TestCase):

    def setUp(self):
        """Set up common test components."""
        self.mock_model = MagicMock()
        # Common Gurobi variables for testing
        self.var1 = create_mock_gurobi_var(0.5, "status[0]")
        self.var2 = create_mock_gurobi_var(1.0, "status[1]")
        self.var3 = create_mock_gurobi_var(0.0, "other[0]")
        self.var4 = create_mock_gurobi_var(0.2, "status[2]")
        self.var5 = create_mock_gurobi_var(0.8, "another_status[0]")  # Different prefix

    def test_get_variables(self):
        """Test extraction of non-binary variables from a Gurobi model."""
        self.mock_model.getVars.return_value = [
            self.var1,
            self.var2,
            self.var3,
            self.var4,
            self.var5,
        ]

        # Test with default target_varnames (should be ["status"])
        result_default = rounding_algo.get_variables(self.mock_model)
        self.assertEqual(len(result_default), 3)  # status[0], status[1], status[2]
        self.assertIn("status[0]", result_default)
        self.assertIn("status[1]", result_default)
        self.assertIn("status[2]", result_default)
        self.assertEqual(result_default["status[0]"], self.var1)

        # Test with custom target_varnames
        result_custom = rounding_algo.get_variables(
            self.mock_model, target_varnames=["status", "another_status"]
        )
        self.assertEqual(len(result_custom), 4)
        self.assertIn("status[0]", result_custom)
        self.assertIn("another_status[0]", result_custom)
        self.assertNotIn("other[0]", result_custom)

        # Test with a target_varname that matches no variables
        result_none = rounding_algo.get_variables(
            self.mock_model, target_varnames=["nonexistent"]
        )
        self.assertEqual(len(result_none), 0)

        # Test with an empty model
        self.mock_model.getVars.return_value = []
        result_empty = rounding_algo.get_variables(self.mock_model)
        self.assertEqual(len(result_empty), 0)

    def test_find_fraction_vars(self):
        """Test finding variables with fractional values."""
        binary_vars = {
            "var_frac1": create_mock_gurobi_var(0.5),
            "var_zero": create_mock_gurobi_var(0.0),
            "var_one": create_mock_gurobi_var(1.0),
            "var_frac2": create_mock_gurobi_var(0.00001),
            "var_near_one": create_mock_gurobi_var(0.999999),
            "var_exact_frac": create_mock_gurobi_var(0.333),
        }

        fractional = rounding_algo.find_fraction_vars(binary_vars)  # Default atol=1e-5
        self.assertIn("var_frac1", fractional)
        self.assertIn("var_exact_frac", fractional)
        self.assertNotIn("var_zero", fractional)
        self.assertNotIn("var_one", fractional)
        # For default atol=1e-5:
        # np.isclose(0.00001, 0, atol=1e-5) is True
        # np.isclose(0.999999, 1, atol=1e-5) is True
        self.assertNotIn("var_frac2", fractional)
        self.assertNotIn("var_near_one", fractional)

        # Test with custom atol
        binary_vars_custom_atol = {
            "var_frac_strict": create_mock_gurobi_var(0.000001),  # 1e-6
            "var_near_one_strict": create_mock_gurobi_var(1 - 1e-6),  # 0.999999
        }
        # With atol=1e-7:
        # np.isclose(1e-6, 0, atol=1e-7) is False -> fractional
        # np.isclose(1 - 1e-6, 1, atol=1e-7) is True (diff is 1e-6, atol+rtol*abs(b) = 1e-7 + 1e-5*1 = 1.01e-5. 1e-6 <= 1.01e-5)
        fractional_custom_atol = rounding_algo.find_fraction_vars(
            binary_vars_custom_atol, atol=1e-7
        )
        self.assertIn(
            "var_frac_strict", fractional_custom_atol
        )  # 1e-6 is not close to 0 with atol 1e-7
        self.assertNotIn(
            "var_near_one_strict", fractional_custom_atol
        )  # Corrected: 1-1e-6 IS close to 1 with atol 1e-7 and default rtol

        # Test with no fractional variables
        no_fractional_vars = {
            "v1": create_mock_gurobi_var(0.0),
            "v2": create_mock_gurobi_var(1.0),
        }
        self.assertEqual(len(rounding_algo.find_fraction_vars(no_fractional_vars)), 0)

        # Test with empty input
        self.assertEqual(len(rounding_algo.find_fraction_vars({})), 0)

    def test_round_up(self):
        """Test rounding a variable up."""
        mock_var = create_mock_gurobi_var(0.5)
        rounding_algo.round_up(mock_var)
        self.assertEqual(mock_var.lb, 1)
        self.assertEqual(mock_var.ub, 1)

    def test_round_down(self):
        """Test rounding a variable down."""
        mock_var = create_mock_gurobi_var(0.5)
        rounding_algo.round_down(mock_var)
        self.assertEqual(mock_var.lb, 0)
        self.assertEqual(mock_var.ub, 0)

    @patch("pownet.optim_model.rounding_algo.round_up")
    @patch("pownet.optim_model.rounding_algo.round_down")
    def test_slow_rounding(self, mock_round_down, mock_round_up):
        """Test the slow_rounding strategy."""
        v_max = create_mock_gurobi_var(0.8, "v_max")
        v_mid = create_mock_gurobi_var(0.5, "v_mid")
        v_low = create_mock_gurobi_var(0.2, "v_low")
        fraction_vars = {"v_max": v_max, "v_mid": v_mid, "v_low": v_low}

        rounding_algo.slow_rounding(fraction_vars, threshold=0.7)
        mock_round_up.assert_called_once_with(v_max)
        mock_round_down.assert_not_called()
        mock_round_up.reset_mock()

        rounding_algo.slow_rounding(fraction_vars, threshold=0.9)
        mock_round_down.assert_called_once_with(v_max)
        mock_round_up.assert_not_called()
        mock_round_down.reset_mock()

        rounding_algo.slow_rounding(fraction_vars, threshold=0)
        mock_round_up.assert_called_once_with(v_max)
        mock_round_down.assert_not_called()
        mock_round_up.reset_mock()

        v_max1 = create_mock_gurobi_var(0.8, "v_max1")
        v_max2 = create_mock_gurobi_var(0.8, "v_max2")
        v_other = create_mock_gurobi_var(0.3, "v_other")
        fraction_vars_multi_max = {
            "v_max1": v_max1,
            "v_max2": v_max2,
            "v_other": v_other,
        }
        rounding_algo.slow_rounding(fraction_vars_multi_max, threshold=0.5)
        self.assertEqual(mock_round_up.call_count, 2)
        mock_round_up.assert_any_call(v_max1)
        mock_round_up.assert_any_call(v_max2)
        mock_round_down.assert_not_called()
        mock_round_up.reset_mock()

        with self.assertRaises(ValueError):
            rounding_algo.slow_rounding({}, threshold=0.5)

    @patch("pownet.optim_model.rounding_algo.round_up")
    @patch("pownet.optim_model.rounding_algo.round_down")
    def test_fast_rounding(self, mock_round_down, mock_round_up):
        """Test the fast_rounding strategy."""
        v_above = create_mock_gurobi_var(0.8, "v_above")
        v_equal = create_mock_gurobi_var(0.5, "v_equal")
        v_below = create_mock_gurobi_var(0.2, "v_below")
        fraction_vars = {"v_above": v_above, "v_equal": v_equal, "v_below": v_below}

        threshold = 0.5
        rounding_algo.fast_rounding(fraction_vars, threshold=threshold)

        mock_round_up.assert_any_call(v_above)
        mock_round_up.assert_any_call(v_equal)
        mock_round_down.assert_called_once_with(v_below)
        self.assertEqual(mock_round_up.call_count, 2)
        mock_round_up.reset_mock()
        mock_round_down.reset_mock()

        fraction_vars_all_above = {
            "v1": create_mock_gurobi_var(0.6),
            "v2": create_mock_gurobi_var(0.9),
        }
        rounding_algo.fast_rounding(fraction_vars_all_above, threshold=0.5)
        self.assertEqual(mock_round_up.call_count, 2)
        mock_round_down.assert_not_called()
        mock_round_up.reset_mock()

        fraction_vars_all_below = {
            "v1": create_mock_gurobi_var(0.1),
            "v2": create_mock_gurobi_var(0.4),
        }
        rounding_algo.fast_rounding(fraction_vars_all_below, threshold=0.5)
        self.assertEqual(mock_round_down.call_count, 2)
        mock_round_up.assert_not_called()

    @patch("pownet.optim_model.rounding_algo.logger")
    def test_check_binary_values(self, mock_logger):
        """Test checking if all variable values are binary."""
        all_binary_vars = {
            "v1": create_mock_gurobi_var(0.0),
            "v2": create_mock_gurobi_var(1.0),
        }
        self.assertTrue(rounding_algo.check_binary_values(all_binary_vars))
        mock_logger.info.assert_not_called()

        one_non_binary_vars = {
            "v1": create_mock_gurobi_var(0.0),
            "v2": create_mock_gurobi_var(0.5),
        }
        self.assertFalse(rounding_algo.check_binary_values(one_non_binary_vars))
        mock_logger.info.assert_called_once_with(
            "Variable v2 has non-binary value: 0.5"
        )
        mock_logger.reset_mock()

        multi_non_binary = {
            "v_frac1": create_mock_gurobi_var(0.3),
            "v_frac2": create_mock_gurobi_var(0.7),
        }
        self.assertFalse(rounding_algo.check_binary_values(multi_non_binary))
        mock_logger.info.assert_called_once_with(
            "Variable v_frac1 has non-binary value: 0.3"
        )
        mock_logger.reset_mock()

        self.assertTrue(rounding_algo.check_binary_values({}))
        mock_logger.info.assert_not_called()

    @patch("pownet.optim_model.rounding_algo.logger")
    @patch("pownet.optim_model.rounding_algo.fast_rounding")
    @patch("pownet.optim_model.rounding_algo.slow_rounding")
    @patch("pownet.optim_model.rounding_algo.find_fraction_vars")
    @patch("pownet.optim_model.rounding_algo.get_variables")
    def test_optimize_with_rounding(
        self,
        mock_get_variables,
        mock_find_fraction_vars,
        mock_slow_rounding,
        mock_fast_rounding,
        mock_logger,
    ):
        """Test the main optimize_with_rounding function."""
        initial_model = MagicMock(spec=rounding_algo.gp.Model)
        initial_model.Params = MagicMock()

        mock_relaxed_model = MagicMock(spec=rounding_algo.gp.Model)
        mock_relaxed_model.Params = MagicMock()
        initial_model.relax.return_value = mock_relaxed_model

        default_params = {
            "rounding_strategy": "fast",
            "threshold": 0.5,
            "max_rounding_iter": 10,
            "mipgap": 0.01,
            "timelimit": 100,
            "num_threads": 4,
            "log_to_console": False,
        }

        # --- Scenario 1: Solves in first iteration ---
        mock_get_variables.return_value = {"status[0]": self.var1}
        mock_find_fraction_vars.side_effect = [{}]
        mock_relaxed_model.optimize = MagicMock()  # Fresh mock for optimize
        mock_relaxed_model.status = 2
        mock_relaxed_model.runtime = 10.0

        result_model, time, iters = rounding_algo.optimize_with_rounding(
            initial_model, **default_params
        )

        initial_model.relax.assert_called_once()
        mock_get_variables.assert_called_once_with(mock_relaxed_model)
        mock_relaxed_model.optimize.assert_called_once()
        mock_find_fraction_vars.assert_called_once_with({"status[0]": self.var1})
        mock_fast_rounding.assert_not_called()
        self.assertEqual(result_model, mock_relaxed_model)
        self.assertEqual(time, 10.0)
        self.assertEqual(iters, 0)
        self.assertEqual(initial_model.Params.LogToConsole, False)
        self.assertEqual(initial_model.Params.MIPGap, 0.01)
        self.assertEqual(mock_relaxed_model.Params.LogToConsole, False)

        # Reset mocks for next scenario
        initial_model.reset_mock()
        initial_model.Params = MagicMock()  # Re-mock Params after parent reset
        mock_relaxed_model.reset_mock()
        mock_relaxed_model.Params = MagicMock()  # Re-mock Params
        initial_model.relax.return_value = mock_relaxed_model  # Re-establish
        mock_get_variables.reset_mock()
        mock_find_fraction_vars.reset_mock()
        mock_slow_rounding.reset_mock()
        mock_fast_rounding.reset_mock()
        mock_logger.reset_mock()

        # --- Scenario 2: Solves in 3 iterations with "slow" strategy ---
        mock_get_variables.return_value = {"s[0]": self.var1, "s[1]": self.var4}
        frac_vars_iter1 = {"s[0]": self.var1}
        frac_vars_iter2 = {"s[1]": self.var4}
        mock_find_fraction_vars.side_effect = [frac_vars_iter1, frac_vars_iter2, {}]
        mock_relaxed_model.optimize = MagicMock()  # Fresh mock
        mock_relaxed_model.status = 2
        mock_relaxed_model.runtime = 5.0

        params_slow = {
            **default_params,
            "rounding_strategy": "slow",
            "max_rounding_iter": 5,
        }
        result_model, time, iters = rounding_algo.optimize_with_rounding(
            initial_model, **params_slow
        )

        self.assertEqual(mock_relaxed_model.optimize.call_count, 3)
        self.assertEqual(mock_find_fraction_vars.call_count, 3)
        self.assertEqual(mock_slow_rounding.call_count, 2)
        mock_slow_rounding.assert_any_call(fraction_vars=frac_vars_iter1, threshold=0.5)
        mock_slow_rounding.assert_any_call(fraction_vars=frac_vars_iter2, threshold=0.5)
        mock_fast_rounding.assert_not_called()
        self.assertEqual(mock_relaxed_model.update.call_count, 2)
        self.assertEqual(result_model, mock_relaxed_model)
        self.assertEqual(time, 15.0)
        self.assertEqual(iters, 2)

        initial_model.reset_mock()
        initial_model.Params = MagicMock()
        mock_relaxed_model.reset_mock()
        mock_relaxed_model.Params = MagicMock()
        initial_model.relax.return_value = mock_relaxed_model
        mock_get_variables.reset_mock()
        mock_find_fraction_vars.reset_mock()
        mock_slow_rounding.reset_mock()
        mock_fast_rounding.reset_mock()
        mock_logger.reset_mock()

        # --- Scenario 3: Reaches max_rounding_iter ---
        mock_get_variables.return_value = {"s[0]": self.var1}
        mock_find_fraction_vars.side_effect = lambda _: {"s[0]": self.var1}
        mock_relaxed_model.optimize = MagicMock()  # Fresh mock
        mock_relaxed_model.status = 2
        mock_relaxed_model.runtime = 1.0
        initial_model.optimize = MagicMock()

        params_max_iter = {**default_params, "max_rounding_iter": 3}
        result_model, time, iters = rounding_algo.optimize_with_rounding(
            initial_model, **params_max_iter
        )

        self.assertEqual(mock_relaxed_model.optimize.call_count, 3)
        self.assertEqual(mock_find_fraction_vars.call_count, 3)
        self.assertEqual(mock_fast_rounding.call_count, 3)
        mock_logger.warning.assert_called_once_with(
            "\nPowNet: The rounding heuristic has terminated before finding an integer solution."
        )
        initial_model.optimize.assert_called_once()
        self.assertEqual(result_model, initial_model)
        self.assertIsNone(time)
        self.assertIsNone(iters)

        initial_model.reset_mock()
        initial_model.Params = MagicMock()
        mock_relaxed_model.reset_mock()
        mock_relaxed_model.Params = MagicMock()
        initial_model.relax.return_value = mock_relaxed_model
        mock_get_variables.reset_mock()
        mock_find_fraction_vars.reset_mock()
        mock_slow_rounding.reset_mock()
        mock_fast_rounding.reset_mock()
        mock_logger.reset_mock()

        # --- Scenario 4: Rounding becomes infeasible (status 3) ---
        mock_get_variables.return_value = {"s[0]": self.var1}
        # Ensure find_fraction_vars returns a value that keeps the loop going once
        mock_find_fraction_vars.side_effect = [
            {"s[0]": create_mock_gurobi_var(0.5, "s[0]")}
        ]

        # Explicitly manage the optimize mock for this scenario to control its side_effect precisely
        # This optimize mock belongs to mock_relaxed_model
        mock_relaxed_model.optimize = MagicMock()
        mock_relaxed_model.optimize.side_effect = (
            None  # Clear any prior side_effect from reset
        )

        mock_relaxed_model.status_sequence = [2, 3]  # Status for 1st call, 2nd call
        mock_relaxed_model.current_call_idx_for_status = (
            0  # Use a unique attribute name
        )

        def optimize_side_effect_scen4():
            # Set status based on the call sequence
            idx = mock_relaxed_model.current_call_idx_for_status
            if idx < len(mock_relaxed_model.status_sequence):
                mock_relaxed_model.status = mock_relaxed_model.status_sequence[idx]
            # If called more times, status remains as last set (or could define error)
            mock_relaxed_model.current_call_idx_for_status += 1
            mock_relaxed_model.runtime = 2.0  # Set runtime for each call
            # model.optimize() typically returns None

        mock_relaxed_model.optimize.side_effect = optimize_side_effect_scen4
        initial_model.optimize = MagicMock()  # Mock for the fallback

        result_model, time, iters = rounding_algo.optimize_with_rounding(
            initial_model, **default_params
        )

        self.assertEqual(
            mock_relaxed_model.optimize.call_count, 2
        )  # Should be called twice
        mock_logger.warning.assert_called_once_with(
            "\nPowNet: Rounding is infeasible. Use the MIP method."
        )
        initial_model.optimize.assert_called_once()
        self.assertEqual(result_model, initial_model)
        self.assertIsNone(time)
        self.assertIsNone(iters)

        initial_model.reset_mock()
        initial_model.Params = MagicMock()
        mock_relaxed_model.reset_mock()
        mock_relaxed_model.Params = MagicMock()
        initial_model.relax.return_value = mock_relaxed_model
        mock_get_variables.reset_mock()
        mock_find_fraction_vars.reset_mock()
        mock_slow_rounding.reset_mock()
        mock_fast_rounding.reset_mock()
        mock_logger.reset_mock()

        # --- Scenario 5: Unrecognized model status ---
        mock_get_variables.return_value = {"s[0]": self.var1}
        mock_relaxed_model.optimize = MagicMock()  # Fresh mock
        mock_relaxed_model.status = 99
        mock_relaxed_model.runtime = 1.0

        with self.assertRaises(ValueError) as context:
            rounding_algo.optimize_with_rounding(initial_model, **default_params)
        self.assertTrue("Unrecognized model status: 99" in str(context.exception))
        mock_relaxed_model.optimize.assert_called_once()


if __name__ == "__main__":
    unittest.main()
