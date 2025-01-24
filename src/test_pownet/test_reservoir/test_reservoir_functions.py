""" test_reservoir_functions.py
"""

import unittest

import pandas as pd

from pownet.reservoir.reservoir_functions import (
    adjust_hydropeaking,
    calc_target_level,
    calc_target_storage,
    calc_daily_hydropower,
)


class TestAdjustHydropeaking(unittest.TestCase):

    def test_no_change_needed(self):
        """Test when the release is already within bounds and no adjustment is needed."""
        result = adjust_hydropeaking(
            release=50, release_t0=45, max_release=100, min_release=20
        )
        self.assertEqual(result, 50)  # No change expected

    def test_increase_within_limit(self):
        """Test when the release needs to increase, but the change is within the hydropeaking limit."""
        result = adjust_hydropeaking(
            release=60,
            release_t0=40,
            max_release=100,
            min_release=20,
            hydropeak_factor=0.2,
        )
        self.assertEqual(result, 60)  # Increase allowed

    def test_increase_exceeds_limit(self):
        """Test when the release needs to increase, but the change exceeds the hydropeaking limit."""
        result = adjust_hydropeaking(
            release=80,
            release_t0=30,
            max_release=100,
            min_release=20,
            hydropeak_factor=0.1,
        )
        self.assertEqual(result, 40)  # Increase limited by hydropeaking factor

    def test_decrease_below_minimum(self):
        """Test when the release needs to decrease, but the adjusted value would be below the minimum."""
        result = adjust_hydropeaking(
            release=15,
            release_t0=40,
            max_release=100,
            min_release=20,
            hydropeak_factor=0.3,
        )
        self.assertEqual(result, 20)  # Decrease limited by minimum release

    def test_enforce_minimum(self):
        """Test when the adjusted release needs to be enforced to the minimum."""
        release = 10
        release_t0 = 30
        max_release = 100
        min_release = 20
        hydropeak_factor = 0.15

        expected_release = 20  # Enforced to minimum
        actual_release = adjust_hydropeaking(
            release, release_t0, max_release, min_release, hydropeak_factor
        )
        self.assertEqual(actual_release, expected_release)

    def test_enforce_maximum(self):
        """Test when the adjusted release needs to be enforced to the maximum."""
        release = 120
        release_t0 = 80
        max_release = 100
        min_release = 20
        hydropeak_factor = 0.20

        expected_release = 100  # Enforced to maximum
        actual_release = adjust_hydropeaking(
            release, release_t0, max_release, min_release, hydropeak_factor
        )
        self.assertEqual(actual_release, expected_release)


class TestCalcTargetLevel(unittest.TestCase):

    def test_basic_interpolation(self):
        """Test basic linear interpolation between min_day and max_day."""
        min_day = 100
        max_day = 200
        min_level = 5.0
        max_level = 10.0

        target_levels = calc_target_level(min_day, max_day, min_level, max_level)

        # Check specific values
        self.assertAlmostEqual(
            target_levels[min_day], min_level
        )  # Min level on min_day
        self.assertAlmostEqual(
            target_levels[max_day], max_level
        )  # Max level on max_day
        self.assertAlmostEqual(target_levels[(min_day + max_day) // 2], 7.5)  # Midpoint

    def test_interpolation_after_max(self):
        """Test interpolation for days after max_day."""
        min_day = 50
        max_day = 150
        min_level = 0.0
        max_level = 100.0

        target_levels = calc_target_level(min_day, max_day, min_level, max_level)

        # Check values after max_day
        self.assertAlmostEqual(target_levels[max_day + 1], 264 / 265 * 100)
        self.assertAlmostEqual(target_levels[365], 50 / 265 * 100)

    def test_interpolation_before_min(self):
        """Test interpolation for days before min_day."""
        min_day = 100
        max_day = 300
        min_level = 20.0
        max_level = 80.0

        target_levels = calc_target_level(min_day, max_day, min_level, max_level)

        # Check values before min_day
        self.assertAlmostEqual(target_levels[min_day - 1], 60 / 165 + 20)
        self.assertAlmostEqual(target_levels[1], (99 / 165 * 60) + 20)


class TestCalcTargetStorage(unittest.TestCase):

    def test_basic_calculation(self):
        """Test basic storage calculation with varying target levels."""
        target_level = pd.Series(
            [25.0, 50.0, 75.0], index=range(1, 4)
        )  # Example target levels
        min_level = 0.0
        max_level = 100.0
        max_storage = 1000.0

        expected_storage = pd.Series([250.0, 500.0, 750.0], index=range(1, 4))
        actual_storage = calc_target_storage(
            target_level, min_level, max_level, max_storage
        )

        pd.testing.assert_series_equal(actual_storage, expected_storage)


class TestCalcDailyHydropower(unittest.TestCase):

    def test_basic_calculation(self):
        def _calc_hydropower(release, mid_level, max_head, max_level):
            return (
                min(
                    0.85
                    * 998
                    * 9.81
                    * (max_head - (max_level - mid_level))
                    * (release / (24 * 3600))
                    / 1e6,
                    10.0,
                )
                * 24
            )

        """Test basic hydropower calculation with typical values."""
        release = pd.Series(
            [100000.0, 200000.0, 300000.0],
            index=range(1, 4),
        )  # Example release values (m3/day)
        mid_level = pd.Series(
            [90.0, 95.0, 100.0], index=range(1, 4)
        )  # Example mid-level values (m)
        max_generation = 10.0  # MW
        turbine_factor = 0.85
        max_head = 100.0  # m
        max_level = 105.0  # m

        # Calculate expected hydropower based on the formula
        expected_hydropower = pd.Series(
            [
                _calc_hydropower(release[1], mid_level[1], max_head, max_level),
                _calc_hydropower(release[2], mid_level[2], max_head, max_level),
                _calc_hydropower(release[3], mid_level[3], max_head, max_level),
            ],
            index=range(1, 4),
        )

        actual_hydropower = calc_daily_hydropower(
            release, mid_level, max_generation, turbine_factor, max_head, max_level
        )

        pd.testing.assert_series_equal(actual_hydropower, expected_hydropower)

    def test_max_generation_limit(self):
        """Test if hydropower is limited by max_generation."""
        release = pd.Series(
            [1000000.0],
        )  # Large release to potentially exceed max_generation
        mid_level = pd.Series([100.0])  # Example mid-level value (m)
        max_generation = 5.0  # MW
        turbine_factor = 0.9
        max_head = 50.0  # m
        max_level = 100.0  # m

        expected_hydropower = pd.Series(
            [max_generation * 24]
        )  # Hydropower limited to max_generation
        actual_hydropower = calc_daily_hydropower(
            release, mid_level, max_generation, turbine_factor, max_head, max_level
        )

        pd.testing.assert_series_equal(actual_hydropower, expected_hydropower)

    # def test_no_level_change(self):
    #     """Test when no level change with output at max head"""
    #     release = pd.Series([100000.0])
    #     mid_level = pd.Series(
    #         [105.0]
    #     )  # mid_level equals max_level, resulting in zero head
    #     max_generation = 10.0
    #     turbine_factor = 0.8
    #     max_head = 20.0
    #     max_level = 105.0

    #     expected_hydropower = pd.Series([0.0])
    #     actual_hydropower = calc_daily_hydropower(
    #         release, mid_level, max_generation, turbine_factor, max_head, max_level
    #     )

    #     pd.testing.assert_series_equal(actual_hydropower, expected_hydropower)


if __name__ == "__main__":
    unittest.main()
