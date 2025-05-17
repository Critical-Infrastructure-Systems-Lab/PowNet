"test_coupler.py"

import unittest
from unittest.mock import MagicMock, PropertyMock, call
import logging

# Assuming coupler.py is in the same directory or accessible via PYTHONPATH
from pownet.coupler import PowerWaterCoupler

# For type hinting if needed
from pownet import ModelBuilder as ActualModelBuilder
from pownet.reservoir import ReservoirManager as ActualReservoirManager

# Disable logging for cleaner test output
logging.disable(logging.CRITICAL)


class TestPowerWaterCoupler(unittest.TestCase):

    def setUp(self):
        """Common setup for all tests."""
        self.mock_model_builder = MagicMock(spec=ActualModelBuilder)
        self.mock_reservoir_manager = MagicMock(spec=ActualReservoirManager)

        # --- Configure ModelBuilder Mock ---
        mock_mb_inputs = MagicMock()
        mock_mb_inputs.sim_horizon = 48  # Allows num_days_in_step = 2
        type(self.mock_model_builder).inputs = PropertyMock(return_value=mock_mb_inputs)

        self.mock_power_system_model = MagicMock()
        self.mock_power_system_model.get_runtime.return_value = 0.5
        self.mock_model_builder.update_daily_hydropower_capacity.return_value = (
            self.mock_power_system_model
        )
        self.mock_model_builder.get_phydro.return_value = {}

        # --- Configure ReservoirManager Mock ---
        self.mock_reservoir_manager.simulation_order = ["H1", "H2"]
        self.mock_reservoir_manager.reoperate.return_value = {}

        self.coupler = PowerWaterCoupler(
            model_builder=self.mock_model_builder,
            reservoir_manager=self.mock_reservoir_manager,
            solver="test_solver",
            mip_gap=0.001,
            timelimit=300,
            log_to_console=False,
        )
        # num_days_in_step should be 2 based on sim_horizon = 48
        self.assertEqual(self.coupler.num_days_in_step, 2)

    def _create_mock_dispatch_var(self, value):
        mock_var = MagicMock()
        mock_var.X = value
        return mock_var

    def test_initialization(self):
        self.assertIs(self.coupler.model_builder, self.mock_model_builder)
        self.assertEqual(self.coupler.num_days_in_step, 2)
        self.assertEqual(self.coupler.reop_iter, [])
        self.assertEqual(self.coupler.reop_opt_time, 0.0)

    def test_getters(self):
        self.coupler.reop_opt_time = 10.5
        self.assertEqual(self.coupler.get_reop_opt_time(), 10.5)
        self.coupler.reop_iter = [1, 2, 3]
        self.assertEqual(self.coupler.get_reop_iter(), [1, 2, 3])

    def test_reoperate_converges_immediately_multi_day(self):
        step_k = 10  # 1-indexed global start day
        # num_days_in_step is 2, so days_in_step = range(10, 12) -> global days 10, 11

        # Hydropower dispatch from ModelBuilder (hourly, spanning 48 hours)
        # varname[1] is 1-indexed hour in ModelBuilder's 48h horizon
        initial_phydro = {
            # Day step_k (Global Day 10)
            ("H1", 1): self._create_mock_dispatch_var(1.0),  # Hour 1, Day 10
            ("H1", 24): self._create_mock_dispatch_var(1.0),  # Hour 24, Day 10
            ("H2", 1): self._create_mock_dispatch_var(0.5),  # Hour 1, Day 10
            ("H2", 24): self._create_mock_dispatch_var(0.5),  # Hour 24, Day 10
            # Day step_k + 1 (Global Day 11)
            ("H1", 25): self._create_mock_dispatch_var(2.0),  # Hour 25, Day 11
            ("H1", 48): self._create_mock_dispatch_var(2.0),  # Hour 48, Day 11
            ("H2", 25): self._create_mock_dispatch_var(1.5),  # Hour 25, Day 11
            ("H2", 48): self._create_mock_dispatch_var(1.5),  # Hour 48, Day 11
        }
        # Assuming 1.0 MW for all 24h of Day 10 for H1, 0.5 MW for H2 on Day 10
        # Assuming 2.0 MW for all 24h of Day 11 for H1, 1.5 MW for H2 on Day 11
        h1_day10_total = 24 * 1.0
        h2_day10_total = 24 * 0.5
        h1_day11_total = 24 * 2.0
        h2_day11_total = 24 * 1.5

        # Populate full hourly data for mock
        current_phydro_mock = {}
        for h in range(1, 25):  # Global Day step_k
            current_phydro_mock[("H1", h)] = self._create_mock_dispatch_var(1.0)
            current_phydro_mock[("H2", h)] = self._create_mock_dispatch_var(0.5)
        for h in range(25, 49):  # Global Day step_k + 1
            current_phydro_mock[("H1", h)] = self._create_mock_dispatch_var(2.0)
            current_phydro_mock[("H2", h)] = self._create_mock_dispatch_var(1.5)
        self.mock_model_builder.get_phydro.return_value = current_phydro_mock

        proposed_capacity_match = {
            ("H1", step_k): h1_day10_total,  # Global Day 10
            ("H2", step_k): h2_day10_total,  # Global Day 10
            ("H1", step_k + 1): h1_day11_total,  # Global Day 11
            ("H2", step_k + 1): h2_day11_total,  # Global Day 11
        }
        self.mock_reservoir_manager.reoperate.return_value = proposed_capacity_match

        self.coupler.reoperate(step_k=step_k)

        expected_daily_dispatch = (
            proposed_capacity_match  # In this case, they are identical
        )
        self.mock_reservoir_manager.reoperate.assert_called_once_with(
            daily_dispatch=expected_daily_dispatch,
            days_in_step=range(step_k, step_k + 2),  # Global days 10, 11
        )
        self.mock_model_builder.update_daily_hydropower_capacity.assert_called_once_with(
            step_k=step_k, new_capacity=proposed_capacity_match
        )
        self.assertEqual(self.coupler.reop_opt_time, 0.5)
        self.assertEqual(self.coupler.reop_iter, [1])

    def test_reoperate_converges_after_iterations_single_day_focus(self):
        """Test convergence over iterations, focusing on one day for simplicity."""
        step_k = 50
        # Temporarily override sim_horizon for this test to focus on single day num_days_in_step = 1
        mock_mb_inputs_24h = MagicMock()
        mock_mb_inputs_24h.sim_horizon = 24
        type(self.mock_model_builder).inputs = PropertyMock(
            return_value=mock_mb_inputs_24h
        )
        # Re-initialize coupler with this specific setup for num_days_in_step = 1
        coupler_single_day = PowerWaterCoupler(
            model_builder=self.mock_model_builder,
            reservoir_manager=self.mock_reservoir_manager,
        )
        self.assertEqual(coupler_single_day.num_days_in_step, 1)
        self.mock_reservoir_manager.simulation_order = ["H1"]

        # Iteration 1: PowNet: 100 (sum for day step_k), Reservoir: 120
        phydro_iter1_hourly = {
            ("H1", h): self._create_mock_dispatch_var(100 / 24) for h in range(1, 25)
        }
        capacity_iter1 = {("H1", step_k): 120.0}

        # Iteration 2: PowNet: 115, Reservoir: 116 (converged: |116-115|=1 <= 0.05*115=5.75)
        phydro_iter2_hourly = {
            ("H1", h): self._create_mock_dispatch_var(115 / 24) for h in range(1, 25)
        }
        capacity_iter2 = {("H1", step_k): 116.0}

        self.mock_model_builder.get_phydro.side_effect = [
            phydro_iter1_hourly,
            phydro_iter2_hourly,
        ]
        self.mock_reservoir_manager.reoperate.side_effect = [
            capacity_iter1,
            capacity_iter2,
        ]

        initial_optimize_call_count = self.mock_power_system_model.optimize.call_count

        coupler_single_day.reoperate(step_k=step_k)

        # --- MODIFIED ASSERTION START ---
        self.assertEqual(
            len(self.mock_reservoir_manager.reoperate.call_args_list),
            2,
            "Incorrect number of calls to reoperate",
        )

        # Expected conceptual values for dispatch sums
        expected_dispatch_val1 = 100.0
        expected_dispatch_val2 = 115.0

        # Check Call 1
        call1_args, call1_kwargs = self.mock_reservoir_manager.reoperate.call_args_list[
            0
        ]
        self.assertEqual(call1_kwargs["days_in_step"], range(step_k, step_k + 1))
        self.assertIn(("H1", step_k), call1_kwargs["daily_dispatch"])
        self.assertAlmostEqual(
            call1_kwargs["daily_dispatch"][("H1", step_k)],
            expected_dispatch_val1,
            places=7,  # Default is 7, adjust if needed
            msg="Mismatch in daily_dispatch for call 1",
        )

        # Check Call 2
        call2_args, call2_kwargs = self.mock_reservoir_manager.reoperate.call_args_list[
            1
        ]
        self.assertEqual(call2_kwargs["days_in_step"], range(step_k, step_k + 1))
        self.assertIn(("H1", step_k), call2_kwargs["daily_dispatch"])
        self.assertAlmostEqual(
            call2_kwargs["daily_dispatch"][("H1", step_k)],
            expected_dispatch_val2,
            places=7,  # Default is 7, adjust if needed
            msg="Mismatch in daily_dispatch for call 2",
        )
        # --- MODIFIED ASSERTION END ---

        self.assertEqual(coupler_single_day.reop_iter, [2])
        self.assertEqual(
            self.mock_power_system_model.optimize.call_count
            - initial_optimize_call_count,
            2,
        )

    def test_reoperate_max_iterations_reached(self):
        step_k = 300
        test_max_reop_iter = 5  # Use a small number for this test
        expected_optimize_calls = test_max_reop_iter + 1

        # Reset call count before this specific test action
        self.mock_power_system_model.optimize.reset_mock()  # Reset call count and other call attributes

        self.mock_reservoir_manager.simulation_order = ["H1"]

        daily_target_dispatch_sum = sum(
            100 / 24 for _ in range(24)
        )  # ~100.00000000000003
        phydro_hourly_no_converge = {}
        for h in range(1, 25):  # Day step_k
            phydro_hourly_no_converge[("H1", h)] = self._create_mock_dispatch_var(
                daily_target_dispatch_sum / 24
            )
        if self.coupler.num_days_in_step > 1:  # Check if default coupler is multi-day
            for h in range(
                25, 49
            ):  # Day step_k+1 (assuming sim_horizon=48 for self.coupler)
                phydro_hourly_no_converge[("H1", h)] = self._create_mock_dispatch_var(
                    daily_target_dispatch_sum / 24
                )

        self.mock_model_builder.get_phydro.return_value = phydro_hourly_no_converge

        # Reservoir proposes something far off for day step_k
        reoperate_return_value = {("H1", step_k): 50.0}
        if self.coupler.num_days_in_step > 1:
            reoperate_return_value[("H1", step_k + 1)] = (
                daily_target_dispatch_sum  # Matches for day step_k+1
            )

        self.mock_reservoir_manager.reoperate.return_value = reoperate_return_value

        with self.assertRaisesRegex(
            ValueError,
            f"Reservoirs reoperation did not converge after {test_max_reop_iter} iterations",
        ):
            self.coupler.reoperate(step_k=step_k, max_reop_iter=test_max_reop_iter)

        self.assertEqual(
            self.mock_power_system_model.optimize.call_count, expected_optimize_calls
        )
        self.assertEqual(
            self.coupler.reop_iter, []
        )  # Should not append if error raised

    def test_hydropower_dispatch_aggregation_multi_day(self):
        step_k = 1
        phydro_data = {}
        for h_model in range(1, 25):
            phydro_data[("H1", h_model)] = self._create_mock_dispatch_var(1.0)
        for h_model in range(25, 49):
            phydro_data[("H1", h_model)] = self._create_mock_dispatch_var(2.0)
        phydro_data[("H2", 1)] = self._create_mock_dispatch_var(0.0)
        self.mock_model_builder.get_phydro.return_value = phydro_data
        self.mock_reservoir_manager.simulation_order = ["H1", "H2"]

        self.mock_reservoir_manager.reoperate.return_value = {
            ("H1", step_k): 24.0,
            ("H1", step_k + 1): 48.0,
            ("H2", step_k): 0.0,
            ("H2", step_k + 1): 0.0,
        }

        # This test uses the default max_reop_iter = 100
        self.coupler.reoperate(step_k=step_k)

        expected_dispatch_to_reservoir = {
            ("H1", step_k): 24.0,
            ("H1", step_k + 1): 48.0,
            ("H2", step_k): 0.0,
            ("H2", step_k + 1): 0.0,
        }
        self.mock_reservoir_manager.reoperate.assert_called_once_with(
            daily_dispatch=expected_dispatch_to_reservoir,
            days_in_step=range(step_k, step_k + 2),
        )
        self.assertEqual(self.coupler.reop_iter, [1])


if __name__ == "__main__":
    unittest.main(argv=["first-arg-is-ignored"], exit=False)
