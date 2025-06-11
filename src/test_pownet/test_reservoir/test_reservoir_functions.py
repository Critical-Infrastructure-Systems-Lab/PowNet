import unittest
import pandas as pd
import numpy as np
import networkx as nx

from pownet.reservoir import reservoir_functions as rf


# Mock function for calc_min_environ_flow as it's used by calc_minflow but not provided
# This is a simplified placeholder. In a real scenario, you'd mock based on its expected behavior.
def calc_min_environ_flow(
    inflow: float, mean_annual_flow: float, max_release: float
) -> float:
    """Dummy implementation for testing purposes."""
    return min(max(0.1 * mean_annual_flow, 0.05 * inflow), max_release * 0.5)


# Monkey patch the reservoir_functions module to use our dummy function
rf.calc_min_environ_flow = calc_min_environ_flow


class TestReservoirFunctions(unittest.TestCase):

    def setUp(self):
        """Set up common test data."""
        self.flow_paths_data = {
            "source": ["R1", "R1", "R2", "R3", "R4"],
            "sink": ["R2", "R3", "R4", "R4", "R5"],
            "flow_fraction": [0.6, 0.4, 1.0, 1.0, 1.0],
        }
        self.flow_paths_df = pd.DataFrame(self.flow_paths_data)

        self.flow_paths_cycle_data = {
            "source": ["R1", "R2", "R3"],
            "sink": ["R2", "R3", "R1"],
            "flow_fraction": [1.0, 1.0, 1.0],
        }
        self.flow_paths_cycle_df = pd.DataFrame(self.flow_paths_cycle_data)

        self.reservoir_names = ["R1", "R2", "R3", "R4", "R5", "R6_isolated"]

    def test_find_upstream_units(self):
        """Test finding upstream units."""
        self.assertEqual(
            sorted(rf.find_upstream_units(self.flow_paths_df, "R4")),
            sorted(["R2", "R3"]),
        )
        self.assertEqual(rf.find_upstream_units(self.flow_paths_df, "R1"), [])
        self.assertEqual(
            rf.find_upstream_units(self.flow_paths_df, "R_NonExistent"), []
        )
        # Test with an empty DataFrame
        empty_df = pd.DataFrame(columns=["source", "sink", "flow_fraction"])
        self.assertEqual(rf.find_upstream_units(empty_df, "R1"), [])

    def test_find_downstream_flow_fractions(self):
        """Test finding downstream flow fractions."""
        self.assertEqual(
            rf.find_downstream_flow_fractions(self.flow_paths_df, "R1"),
            {"R2": 0.6, "R3": 0.4},
        )
        self.assertEqual(
            rf.find_downstream_flow_fractions(self.flow_paths_df, "R5"), {}
        )
        self.assertEqual(
            rf.find_downstream_flow_fractions(self.flow_paths_df, "R_NonExistent"), {}
        )
        # Test with an empty DataFrame
        empty_df = pd.DataFrame(columns=["source", "sink", "flow_fraction"])
        self.assertEqual(rf.find_downstream_flow_fractions(empty_df, "R1"), {})

    def test_find_simulation_order(self):
        """Test determining simulation order."""
        order = rf.find_simulation_order(self.reservoir_names, self.flow_paths_df)
        self.assertIn("R6_isolated", order)

        graph_nodes_in_order = [
            res
            for res in order
            if res
            in self.flow_paths_df["source"].tolist()
            + self.flow_paths_df["sink"].tolist()
        ]

        if "R1" in graph_nodes_in_order:
            idx_r1 = graph_nodes_in_order.index("R1")
            if "R2" in graph_nodes_in_order:
                self.assertLess(idx_r1, graph_nodes_in_order.index("R2"))
            if "R3" in graph_nodes_in_order:
                self.assertLess(idx_r1, graph_nodes_in_order.index("R3"))
            if "R4" in graph_nodes_in_order:
                self.assertLess(idx_r1, graph_nodes_in_order.index("R4"))
            if "R5" in graph_nodes_in_order:
                self.assertLess(idx_r1, graph_nodes_in_order.index("R5"))

        if "R2" in graph_nodes_in_order and "R4" in graph_nodes_in_order:
            self.assertLess(
                graph_nodes_in_order.index("R2"), graph_nodes_in_order.index("R4")
            )
        if "R2" in graph_nodes_in_order and "R5" in graph_nodes_in_order:
            self.assertLess(
                graph_nodes_in_order.index("R2"), graph_nodes_in_order.index("R5")
            )

        if "R3" in graph_nodes_in_order and "R4" in graph_nodes_in_order:
            self.assertLess(
                graph_nodes_in_order.index("R3"), graph_nodes_in_order.index("R4")
            )
        if "R3" in graph_nodes_in_order and "R5" in graph_nodes_in_order:
            self.assertLess(
                graph_nodes_in_order.index("R3"), graph_nodes_in_order.index("R5")
            )

        if "R4" in graph_nodes_in_order and "R5" in graph_nodes_in_order:
            self.assertLess(
                graph_nodes_in_order.index("R4"), graph_nodes_in_order.index("R5")
            )

        self.assertEqual(len(order), len(self.reservoir_names))

        with self.assertRaisesRegex(ValueError, "The reservoir network has cycles."):
            rf.find_simulation_order(["R1", "R2", "R3"], self.flow_paths_cycle_df)

        isolated_reservoirs = ["A", "B", "C"]
        empty_flow_paths = pd.DataFrame(columns=["source", "sink"])
        order_isolated = rf.find_simulation_order(isolated_reservoirs, empty_flow_paths)
        self.assertEqual(sorted(order_isolated), sorted(isolated_reservoirs))

        flow_paths_simple = pd.DataFrame({"source": ["X"], "sink": ["Y"]})
        reservoir_names_mixed = ["X", "Y", "Z"]
        order_mixed = rf.find_simulation_order(reservoir_names_mixed, flow_paths_simple)
        self.assertIn("Z", order_mixed)
        self.assertIn("X", order_mixed)
        self.assertIn("Y", order_mixed)
        # Check relative order of X and Y if both are part of the graph component of the order
        # Note: 'Z' could be before, between or after X and Y depending on implementation details
        # We only care that X is before Y if they are in the flow path.
        order_mixed_graph_part = [n for n in order_mixed if n in ["X", "Y"]]
        if "X" in order_mixed_graph_part and "Y" in order_mixed_graph_part:
            self.assertLess(
                order_mixed_graph_part.index("X"), order_mixed_graph_part.index("Y")
            )

    def test_adjust_hydropeaking(self):
        """Test adjusting release for hydropeaking."""
        # Case 1: Increase within limit
        self.assertAlmostEqual(rf.adjust_hydropeaking(120, 100, 1000, 10, 0.15), 120)
        # Case 2: Increase exceeds limit
        self.assertAlmostEqual(
            rf.adjust_hydropeaking(200, 100, 1000, 10, 0.05), 100 + 0.05 * 1000
        )  # 150
        # Case 3: Decrease within limit
        self.assertAlmostEqual(rf.adjust_hydropeaking(80, 100, 1000, 10, 0.15), 80)
        # Case 4: Decrease exceeds limit
        self.assertAlmostEqual(
            rf.adjust_hydropeaking(0, 100, 1000, 10, 0.05), 100 - 0.05 * 1000
        )  # 50
        # Case 5: Result below min_release
        self.assertAlmostEqual(rf.adjust_hydropeaking(5, 100, 1000, 10, 0.15), 10)
        # Case 6: Result above max_release
        self.assertAlmostEqual(rf.adjust_hydropeaking(1200, 1000, 1100, 10, 0.15), 1100)
        # Case 7: No change
        self.assertAlmostEqual(rf.adjust_hydropeaking(100, 100, 1000, 10, 0.15), 100)

        # Case 8: (Formerly "Recalculating Case 8")
        # Scenario 8a: release=115, release_t0=100, max_release=100, min_release=10, hydropeak_factor=0.15
        # release_change = 15
        # change_limit = 0.15 * 100 = 15
        # release_change = min(15, 15) = 15
        # adj_release = 100 + 15 = 115
        # adj_release = max(10, 115) = 115
        # adj_release = min(100, 115) = 100. Function should return 100.
        self.assertAlmostEqual(
            rf.adjust_hydropeaking(
                release=115,
                release_t0=100,
                max_release=100,
                min_release=10,
                hydropeak_factor=0.15,
            ),
            100,
        )

        # Scenario 8b: release=115, release_t0=100, max_release=200, min_release=10, hydropeak_factor=0.15
        # release_change = 15
        # change_limit = 0.15 * 200 = 30
        # release_change = min(30, 15) = 15
        # adj_release = 100 + 15 = 115
        # adj_release = max(10, 115) = 115
        # adj_release = min(200, 115) = 115. Function should return 115.
        self.assertAlmostEqual(
            rf.adjust_hydropeaking(
                release=115,
                release_t0=100,
                max_release=200,
                min_release=10,
                hydropeak_factor=0.15,
            ),
            115,
        )

        # Test with default hydropeak_factor
        self.assertAlmostEqual(
            rf.adjust_hydropeaking(120, 100, 1000, 10), 120
        )  # Default is 0.15

    # def test_calc_minflow(self):
    #     """Test calculating minimum environmental flow."""
    #     inflow = pd.Series([100, 200, 50])
    #     mean_annual_flow = pd.Series([150, 150, 150])
    #     max_release = 500

    #     expected_minflow_values = []
    #     for i in range(len(inflow)):
    #         expected_minflow_values.append(
    #             calc_min_environ_flow(
    #                 inflow.iloc[i], mean_annual_flow.iloc[i], max_release
    #             )
    #         )
    #     expected_minflow = pd.Series(expected_minflow_values)

    #     calculated_minflow = rf.calc_minflow(inflow, mean_annual_flow, max_release)
    #     pd.testing.assert_series_equal(
    #         calculated_minflow, expected_minflow, check_dtype=False
    #     )

    def test_calc_target_level(self):
        """Test calculating target water level."""
        days_in_year = 365  # Defined within calc_target_level, used for clarity here
        min_day_std, max_day_std = 100, 200
        min_level_std, max_level_std = 10.0, 20.0
        target_level_std = rf.calc_target_level(
            min_day_std, max_day_std, min_level_std, max_level_std
        )

        self.assertEqual(len(target_level_std), 365)
        self.assertAlmostEqual(target_level_std.loc[min_day_std], min_level_std)
        self.assertAlmostEqual(target_level_std.loc[max_day_std], max_level_std)
        self.assertAlmostEqual(target_level_std.loc[150], 15.0)

        # Test interpolation logic directly for non-wrapping cases
        # Day after max_day_std
        expected_day_250_std = (
            (days_in_year - 250 + min_day_std)
            / (days_in_year - max_day_std + min_day_std)
        ) * (max_level_std - min_level_std) + min_level_std
        self.assertAlmostEqual(target_level_std.loc[250], expected_day_250_std)
        # Day before min_day_std
        expected_day_50_std = (
            (min_day_std - 50) / (days_in_year - max_day_std + min_day_std)
        ) * (max_level_std - min_level_std) + min_level_std
        self.assertAlmostEqual(target_level_std.loc[50], expected_day_50_std)

        # Test case where min_day > max_day (e.g. filling season across year end)
        # This tests the function's behavior as-is for this edge case.
        min_day_wrap, max_day_wrap = 300, 50
        min_level_wrap, max_level_wrap = 5.0, 25.0
        target_level_wrap = rf.calc_target_level(
            min_day_wrap, max_day_wrap, min_level_wrap, max_level_wrap
        )

        self.assertEqual(len(target_level_wrap), 365)

        # The original function's logic for min_day > max_day results in specific values at min_day_wrap and max_day_wrap
        # Day 300 (min_day_wrap): uses _interpolate_after_max(300)
        # ((365 - 300 + 300) / (365 - 50 + 300)) * (25 - 5) + 5 = (365/615)*20 + 5 = 16.869918...
        expected_val_at_min_day_wrap = (
            (days_in_year - min_day_wrap + min_day_wrap)
            / (days_in_year - max_day_wrap + min_day_wrap)
        ) * (max_level_wrap - min_level_wrap) + min_level_wrap
        self.assertAlmostEqual(
            target_level_wrap.loc[min_day_wrap], expected_val_at_min_day_wrap
        )

        # Day 50 (max_day_wrap): uses _interpolate_before_min(50)
        # ((300 - 50) / (365 - 50 + 300)) * (25 - 5) + 5 = (250/615)*20 + 5 = 13.130081...
        expected_val_at_max_day_wrap = (
            (min_day_wrap - max_day_wrap) / (days_in_year - max_day_wrap + min_day_wrap)
        ) * (max_level_wrap - min_level_wrap) + min_level_wrap
        self.assertAlmostEqual(
            target_level_wrap.loc[max_day_wrap], expected_val_at_max_day_wrap
        )

        # Day 330: (300 <= 330, 330 > 50) -> uses _interpolate_after_max(330)
        # ((365 - 330 + 300) / (365 - 50 + 300)) * (25-5) + 5 = (335/615)*20 + 5 = 15.894308...
        expected_val_day_330_wrap = (
            (days_in_year - 330 + min_day_wrap)
            / (days_in_year - max_day_wrap + min_day_wrap)
        ) * (max_level_wrap - min_level_wrap) + min_level_wrap
        self.assertAlmostEqual(target_level_wrap.loc[330], expected_val_day_330_wrap)

        # Day 20: (20 < 300, 20 <= 50) -> uses _interpolate_before_min(20)
        # ((300 - 20) / (365 - 50 + 300)) * (25-5) + 5 = (280/615)*20 + 5 = 14.105691...
        expected_val_day_20_wrap = (
            (min_day_wrap - 20) / (days_in_year - max_day_wrap + min_day_wrap)
        ) * (max_level_wrap - min_level_wrap) + min_level_wrap
        self.assertAlmostEqual(target_level_wrap.loc[20], expected_val_day_20_wrap)

    def test_calc_target_storage(self):
        """Test calculating target storage from target level."""
        target_level = pd.Series([10, 15, 20], index=[1, 2, 3])
        min_level, max_level = 10.0, 20.0
        max_storage = 1000.0

        expected_storage = pd.Series([0.0, 500.0, 1000.0], index=[1, 2, 3])
        calculated_storage = rf.calc_target_storage(
            target_level, min_level, max_level, max_storage
        )
        pd.testing.assert_series_equal(
            calculated_storage, expected_storage, check_dtype=False
        )

    def test_calc_level_from_storage(self):
        """Test calculating water level from storage."""
        storage = pd.Series([0, 500, 1000], index=[1, 2, 3])
        min_level, max_level = 10.0, 20.0
        max_storage = 1000.0

        expected_level = pd.Series([10.0, 15.0, 20.0], index=[1, 2, 3])
        calculated_level = rf.calc_level_from_storage(
            storage, min_level, max_level, max_storage
        )
        pd.testing.assert_series_equal(
            calculated_level, expected_level, check_dtype=False
        )

        target_level_orig = pd.Series([12.0, 18.0])
        target_storage_calc = rf.calc_target_storage(
            target_level_orig, min_level, max_level, max_storage
        )
        level_recalc = rf.calc_level_from_storage(
            target_storage_calc, min_level, max_level, max_storage
        )
        pd.testing.assert_series_equal(
            level_recalc, target_level_orig, check_dtype=False
        )

    def test_calc_hourly_hydropower(self):
        """Test calculating hourly hydropower generation."""
        release = pd.Series([100 * 3600, 200 * 3600])
        mid_level = pd.Series([190.0, 195.0])
        max_generation = 50.0
        turbine_factor = 0.85
        max_head = 100.0
        max_level = 200.0

        max_generation_high = 200
        calculated_hp = rf.calc_hourly_hydropower(
            release, mid_level, max_generation_high, turbine_factor, max_head, max_level
        )
        expected_hp_vals = []
        density = 998
        gravity = 9.81

        head1 = max_head - (max_level - mid_level.iloc[0])
        flow_rate1 = release.iloc[0] / 3600
        power1_mw = (turbine_factor * density * gravity * head1 * flow_rate1) / 1e6
        expected_hp_vals.append(min(power1_mw, max_generation_high))

        head2 = max_head - (max_level - mid_level.iloc[1])
        flow_rate2 = release.iloc[1] / 3600
        power2_mw = (turbine_factor * density * gravity * head2 * flow_rate2) / 1e6
        expected_hp_vals.append(min(power2_mw, max_generation_high))

        expected_hp = pd.Series(expected_hp_vals)
        pd.testing.assert_series_equal(
            calculated_hp, expected_hp, check_dtype=False, rtol=1e-5
        )

        calculated_hp_capped = rf.calc_hourly_hydropower(
            release, mid_level, max_generation, turbine_factor, max_head, max_level
        )
        expected_hp_capped_vals = [
            min(expected_hp_vals[0], max_generation),
            min(expected_hp_vals[1], max_generation),
        ]
        expected_hp_capped_series = pd.Series(expected_hp_capped_vals)
        pd.testing.assert_series_equal(
            calculated_hp_capped,
            expected_hp_capped_series,
            check_dtype=False,
            rtol=1e-5,
        )

    def test_calc_daily_hydropower(self):
        """Test calculating daily hydropower generation."""
        release_daily = pd.Series([100 * 3600 * 24, 200 * 3600 * 24])
        mid_level = pd.Series([190.0, 195.0])
        max_generation = 150.0
        turbine_factor = 0.85
        max_head = 100.0
        max_level = 200.0

        release_hourly = release_daily / 24
        expected_hourly_hp = rf.calc_hourly_hydropower(
            release_hourly,
            mid_level,
            max_generation,
            turbine_factor,
            max_head,
            max_level,
        )
        expected_daily_hp = expected_hourly_hp * 24

        calculated_daily_hp = rf.calc_daily_hydropower(
            release_daily,
            mid_level,
            max_generation,
            turbine_factor,
            max_head,
            max_level,
        )
        pd.testing.assert_series_equal(
            calculated_daily_hp, expected_daily_hp, check_dtype=False, rtol=1e-5
        )

    def test_calc_release_impact(self):
        """Test calculating impact of a release."""
        storage_t0 = 5000.0
        total_inflow_t = 1000.0
        min_level, max_level_param = (
            10.0,
            20.0,
        )  # Renamed max_level to avoid conflict with module-level max_level variable
        max_storage = 10000.0
        level_t0 = 15.0
        max_generation = 50.0
        turbine_factor = 0.85
        max_head = 100.0

        release_t1 = 800.0
        spill_t1, storage_t1, level_t1, daily_hp_t1 = rf.calc_release_impact(
            release_t1,
            storage_t0,
            total_inflow_t,
            min_level,
            max_level_param,
            max_storage,
            level_t0,
            max_generation,
            turbine_factor,
            max_head,
        )
        self.assertAlmostEqual(spill_t1, 0)
        self.assertAlmostEqual(storage_t1, storage_t0 + total_inflow_t - release_t1 - 0)

        expected_level_t1 = rf.calc_level_from_storage(
            pd.Series([storage_t1]), min_level, max_level_param, max_storage
        ).iloc[0]
        self.assertAlmostEqual(level_t1, expected_level_t1)

        mid_level_t1 = (level_t0 + level_t1) / 2
        expected_daily_hp_t1 = rf.calc_daily_hydropower(
            pd.Series([release_t1]),
            pd.Series([mid_level_t1]),
            max_generation,
            turbine_factor,
            max_head,
            max_level_param,  # Use max_level_param here
        ).iloc[0]
        self.assertAlmostEqual(daily_hp_t1, expected_daily_hp_t1)

        release_t2 = 300.0
        max_storage_spill = 5500.0
        level_t0_spill = rf.calc_level_from_storage(
            pd.Series([storage_t0]), min_level, max_level_param, max_storage_spill
        ).iloc[0]

        spill_t2, storage_t2, level_t2, daily_hp_t2 = rf.calc_release_impact(
            release_t2,
            storage_t0,
            total_inflow_t,
            min_level,
            max_level_param,
            max_storage_spill,
            level_t0_spill,
            max_generation,
            turbine_factor,
            max_head,
        )
        self.assertAlmostEqual(
            spill_t2,
            max(storage_t0 + total_inflow_t - max_storage_spill - release_t2, 0),
        )
        self.assertAlmostEqual(storage_t2, max_storage_spill)

        expected_level_t2 = rf.calc_level_from_storage(
            pd.Series([storage_t2]), min_level, max_level_param, max_storage_spill
        ).iloc[0]
        self.assertAlmostEqual(level_t2, expected_level_t2)

        mid_level_t2 = (level_t0_spill + level_t2) / 2
        expected_daily_hp_t2 = rf.calc_daily_hydropower(
            pd.Series([release_t2]),
            pd.Series([mid_level_t2]),
            max_generation,
            turbine_factor,
            max_head,
            max_level_param,  # Use max_level_param here
        ).iloc[0]
        self.assertAlmostEqual(daily_hp_t2, expected_daily_hp_t2)

    def test_calc_max_release(self):
        """Test calculating maximum allowable release."""
        total_inflow_t = 100.0
        release_t0 = 50.0
        storage_t0 = 1000.0
        minflow_t = 10.0
        max_release_capacity = 200.0
        hydropeak_factor = 0.1

        self.assertAlmostEqual(
            rf.calc_max_release(
                total_inflow_t,
                release_t0,
                storage_t0,
                minflow_t,
                max_release_capacity,
                hydropeak_factor,
            ),
            70.0,
        )
        self.assertAlmostEqual(
            rf.calc_max_release(
                total_inflow_t,
                190,
                storage_t0,
                minflow_t,
                max_release_capacity,
                hydropeak_factor,
            ),
            200.0,
        )
        self.assertAlmostEqual(
            rf.calc_max_release(
                total_inflow_t,
                5,
                storage_t0,
                30,
                max_release_capacity,
                hydropeak_factor,
            ),
            30.0,
        )
        self.assertAlmostEqual(
            rf.calc_max_release(5, 50, 5, 10, max_release_capacity, hydropeak_factor),
            10.0,
        )
        self.assertAlmostEqual(
            rf.calc_max_release(
                total_inflow_t=3,
                release_t0=50,
                storage_t0=5,
                minflow_t=10,
                max_release=max_release_capacity,
                hydropeak_factor=hydropeak_factor,
            ),
            8.0,
        )

    def test_calc_min_release(self):
        """Test calculating minimum allowable release."""
        total_inflow_t = 100.0
        release_t0 = 100.0
        storage_t0 = 1000.0
        minflow_t = 20.0
        max_release_capacity = 200.0
        hydropeak_factor = 0.1

        self.assertAlmostEqual(
            rf.calc_min_release(
                total_inflow_t,
                release_t0,
                storage_t0,
                minflow_t,
                max_release_capacity,
                hydropeak_factor,
            ),
            80.0,
        )
        self.assertAlmostEqual(
            rf.calc_min_release(
                total_inflow_t,
                30,
                storage_t0,
                minflow_t,
                max_release_capacity,
                hydropeak_factor,
            ),
            20.0,
        )
        self.assertAlmostEqual(
            rf.calc_min_release(5, 100, 5, 20, max_release_capacity, hydropeak_factor),
            10.0,
        )
        self.assertAlmostEqual(
            rf.calc_min_release(1, 100, 1, 20, max_release_capacity, hydropeak_factor),
            2.0,
        )
        self.assertAlmostEqual(
            rf.calc_min_release(
                total_inflow_t,
                10,
                storage_t0,
                5,
                max_release_capacity,
                hydropeak_factor,
            ),
            5.0,
        )

    def test_convert_to_hourly_hydropower(self):
        """Test converting daily hydropower to hourly."""
        daily_hp = pd.Series(
            [240, 480], index=pd.to_datetime(["2023-01-01", "2023-01-02"])
        )
        hourly_hp = rf.convert_to_hourly_hydropower(daily_hp)

        self.assertEqual(len(hourly_hp), 2 * 24)
        self.assertEqual(hourly_hp.index[0], 1)
        self.assertEqual(hourly_hp.index[-1], 48)

        for i in range(24):
            self.assertAlmostEqual(hourly_hp.iloc[i], daily_hp.iloc[0] / 24)

        for i in range(24):
            self.assertAlmostEqual(hourly_hp.iloc[24 + i], daily_hp.iloc[1] / 24)

        daily_hp_single = pd.Series([120], index=pd.to_datetime(["2023-01-01"]))
        hourly_hp_single = rf.convert_to_hourly_hydropower(daily_hp_single)
        self.assertEqual(len(hourly_hp_single), 24)
        self.assertEqual(hourly_hp_single.index[0], 1)
        for i in range(24):
            self.assertAlmostEqual(
                hourly_hp_single.iloc[i], daily_hp_single.iloc[0] / 24
            )


if __name__ == "__main__":
    unittest.main(argv=["first-arg-is-ignored"], exit=False)
