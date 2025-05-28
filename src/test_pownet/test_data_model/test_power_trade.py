import unittest
import os
import tempfile
import dataclasses


from pownet.data_model.power_trade import PowerTradeParams

# --- Test Data ---
VALID_INTERTIE_POINTS = [("N1", "N2"), ("N3", "N4")]
VALID_INTERTIE_CAPACITIES = {("N1", "N2"): 100.0, ("N3", "N4"): 200.0}
VALID_CONNECTED_BA = [("BA1", "BA2"), ("BA3", "BA4")]
VALID_TOTAL_TRANSFER_LIMITS = {("BA1", "BA2"): 150.0, ("BA3", "BA4"): 250.0}

CSV_HEADER = "intertie_1_ba,intertie_1_node,intertie_2_ba,intertie_2_node,capacity_mw\n"
VALID_CSV_DATA_ROW1 = "BA1,N1,BA2,N2,100.0\n"
VALID_CSV_DATA_ROW2 = "BA1,N3,BA2,N4,50.5\n"
VALID_CSV_DATA_ROW3 = "BA3,N5,BA4,N6,200.0\n"


class TestPowerTradeParams(unittest.TestCase):
    """Test suite for the PowerTradeParams dataclass and its methods."""

    def _create_temp_csv_file(self, content: str) -> str:
        """
        Helper method to create a temporary CSV file with given content.
        The file is registered for cleanup after the test.
        Returns the path to the temporary file.
        """
        # Use mkstemp for a unique file name and then open it in text mode
        fd, path = tempfile.mkstemp(suffix=".csv", text=True)
        with os.fdopen(fd, "w") as tmp_file:
            tmp_file.write(content)
        self.addCleanup(
            os.remove, path
        )  # Ensures the file is deleted after the test method
        return path

    # --- __init__ and __post_init__ Tests ---

    def test_successful_initialization(self):
        """Test successful instantiation with valid parameters."""
        params = PowerTradeParams(
            intertie_points=VALID_INTERTIE_POINTS,
            intertie_capacities=VALID_INTERTIE_CAPACITIES,
            connected_ba=VALID_CONNECTED_BA,
            total_transfer_limits=VALID_TOTAL_TRANSFER_LIMITS,
        )
        self.assertEqual(params.intertie_points, VALID_INTERTIE_POINTS)
        self.assertEqual(params.intertie_capacities, VALID_INTERTIE_CAPACITIES)
        self.assertEqual(params.connected_ba, VALID_CONNECTED_BA)
        self.assertEqual(params.total_transfer_limits, VALID_TOTAL_TRANSFER_LIMITS)

    def test_default_factory_initialization(self):
        """Test instantiation with default factory values (empty lists/dicts)."""
        params = PowerTradeParams()
        self.assertEqual(params.intertie_points, [])
        self.assertEqual(params.intertie_capacities, {})
        self.assertEqual(params.connected_ba, [])
        self.assertEqual(params.total_transfer_limits, {})

    def test_post_init_negative_intertie_capacity(self):
        """Test __post_init__ raises ValueError for negative intertie capacity."""
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            PowerTradeParams(intertie_capacities={("N1", "N2"): -100.0})

    def test_post_init_self_loop_intertie(self):
        """Test __post_init__ raises ValueError for self-loop in intertie_points."""
        with self.assertRaisesRegex(ValueError, "Self-loop intertie found"):
            PowerTradeParams(intertie_points=[("N1", "N1")])

    def test_post_init_reverse_intertie(self):
        """Test __post_init__ raises ValueError for reverse intertie in intertie_points."""
        with self.assertRaisesRegex(
            ValueError, "Reverse intertie .* found in intertie points"
        ):
            PowerTradeParams(intertie_points=[("N1", "N2"), ("N2", "N1")])

    def test_post_init_reverse_ba_pair(self):
        """Test __post_init__ raises ValueError for reverse BA pair in connected_ba."""
        with self.assertRaisesRegex(
            ValueError, "Reverse BA pair .* found in connected BA"
        ):
            PowerTradeParams(connected_ba=[("BA1", "BA2"), ("BA2", "BA1")])

    # --- from_csv Tests ---

    def test_from_csv_successful_creation(self):
        """Test successful creation of PowerTradeParams from a valid CSV file."""
        csv_content = CSV_HEADER + VALID_CSV_DATA_ROW1 + VALID_CSV_DATA_ROW2
        # BA1,N1,BA2,N2,100.0
        # BA1,N3,BA2,N4,50.5
        temp_csv_path = self._create_temp_csv_file(csv_content)

        params = PowerTradeParams.from_csv(temp_csv_path)

        expected_intertie_points = [("N1", "N2"), ("N3", "N4")]
        expected_intertie_capacities = {("N1", "N2"): 100.0, ("N3", "N4"): 50.5}
        expected_connected_ba = [("BA1", "BA2")]  # Only one BA-BA pair
        expected_total_transfer_limits = {("BA1", "BA2"): 150.5}  # Sum of capacities

        self.assertCountEqual(
            params.intertie_points, expected_intertie_points
        )  # Order might not be guaranteed from set
        self.assertEqual(params.intertie_capacities, expected_intertie_capacities)
        self.assertCountEqual(params.connected_ba, expected_connected_ba)
        self.assertEqual(params.total_transfer_limits, expected_total_transfer_limits)

    def test_from_csv_missing_required_column(self):
        """Test from_csv raises ValueError if a required column is missing."""
        csv_content = "intertie_1_ba,intertie_1_node,intertie_2_ba,capacity_mw\nBA1,N1,BA2,100\n"  # Missing intertie_2_node
        temp_csv_path = self._create_temp_csv_file(csv_content)
        with self.assertRaisesRegex(
            ValueError, "CSV file must contain the following columns"
        ):
            PowerTradeParams.from_csv(temp_csv_path)

    def test_from_csv_duplicate_intertie_in_file(self):
        """Test from_csv raises ValueError for duplicate intertie points in the CSV."""
        csv_content = (
            CSV_HEADER + VALID_CSV_DATA_ROW1 + "BA_X,N1,BA_Y,N2,200.0\n"
        )  # N1-N2 defined twice
        temp_csv_path = self._create_temp_csv_file(csv_content)
        with self.assertRaisesRegex(ValueError, "Duplicate intertie point found"):
            PowerTradeParams.from_csv(temp_csv_path)

    def test_from_csv_invalid_capacity_value(self):
        """Test from_csv raises ValueError if capacity_mw is not a valid float."""
        csv_content = CSV_HEADER + "BA1,N1,BA2,N2,not_a_number\n"
        temp_csv_path = self._create_temp_csv_file(csv_content)
        with self.assertRaises(ValueError) as cm:  # Specific message comes from float()
            PowerTradeParams.from_csv(temp_csv_path)
        self.assertIn("could not convert string to float", str(cm.exception).lower())

    def test_from_csv_headers_only_file(self):
        """Test from_csv with a file containing only headers (no data rows)."""
        temp_csv_path = self._create_temp_csv_file(CSV_HEADER)
        params = PowerTradeParams.from_csv(temp_csv_path)
        self.assertEqual(params.intertie_points, [])
        self.assertEqual(params.intertie_capacities, {})
        self.assertEqual(params.connected_ba, [])
        self.assertEqual(params.total_transfer_limits, {})

    def test_from_csv_truly_empty_file(self):
        """Test from_csv with a completely empty file (0 bytes)."""
        # This should raise an error from pandas.read_csv
        # The typical error is pandas.errors.EmptyDataError
        temp_csv_path = self._create_temp_csv_file("") # Creates an empty file
        
        # Import pandas errors for a more specific check, if desired
        # from pandas.errors import EmptyDataError 
        with self.assertRaises(Exception) as cm:
            PowerTradeParams.from_csv(temp_csv_path)
        
        self.assertIn("no columns to parse", str(cm.exception).lower())

    def test_from_csv_correct_total_transfer_limits_aggregation(self):
        """Test from_csv correctly aggregates capacities for total_transfer_limits."""
        csv_content = (
            CSV_HEADER
            + "BA1,N1,BA2,N2,100.0\n"  # BA1-BA2
            + "BA1,N3,BA2,N4,50.0\n"  # BA1-BA2
            + "BA3,N5,BA4,N6,75.0\n"  # BA3-BA4
        )
        temp_csv_path = self._create_temp_csv_file(csv_content)
        params = PowerTradeParams.from_csv(temp_csv_path)
        expected_limits = {("BA1", "BA2"): 150.0, ("BA3", "BA4"): 75.0}
        self.assertEqual(params.total_transfer_limits, expected_limits)

    # --- from_csv triggering __post_init__ validations ---

    def test_from_csv_validates_negative_capacity(self):
        """Test from_csv leads to __post_init__ validation for negative capacity."""
        csv_content = CSV_HEADER + "BA1,N1,BA2,N2,-100.0\n"
        temp_csv_path = self._create_temp_csv_file(csv_content)
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            PowerTradeParams.from_csv(temp_csv_path)

    def test_from_csv_validates_self_loop_intertie(self):
        """Test from_csv leads to __post_init__ validation for self-loop interties."""
        csv_content = CSV_HEADER + "BA1,N1,BA2,N1,100.0\n"  # N1-N1 intertie
        temp_csv_path = self._create_temp_csv_file(csv_content)
        with self.assertRaisesRegex(ValueError, "Self-loop intertie found"):
            PowerTradeParams.from_csv(temp_csv_path)

    def test_from_csv_validates_reverse_intertie(self):
        """Test from_csv leads to __post_init__ validation for reverse interties."""
        csv_content = (
            CSV_HEADER
            + "BA1,N1,BA2,N2,100.0\n"
            + "BA3,N2,BA4,N1,50.0\n"  # N2-N1 intertie, distinct from N1-N2
        )
        temp_csv_path = self._create_temp_csv_file(csv_content)
        # This should create intertie_points [('N1','N2'), ('N2','N1')] which __post_init__ catches
        with self.assertRaisesRegex(
            ValueError, "Reverse intertie .* found in intertie points"
        ):
            PowerTradeParams.from_csv(temp_csv_path)

    def test_from_csv_validates_reverse_ba_pair(self):
        """Test from_csv leads to __post_init__ validation for reverse BA pairs."""
        csv_content = (
            CSV_HEADER
            + "BA1,N1,BA2,N2,100.0\n"  # Corridor BA1-BA2
            + "BA2,N3,BA1,N4,50.0\n"  # Corridor BA2-BA1
        )
        temp_csv_path = self._create_temp_csv_file(csv_content)
        # This creates connected_ba [('BA1','BA2'), ('BA2','BA1')] which __post_init__ catches
        with self.assertRaisesRegex(
            ValueError, "Reverse BA pair .* found in connected BA"
        ):
            PowerTradeParams.from_csv(temp_csv_path)

    def test_from_csv_allows_self_connected_ba_if_not_reversed(self):
        """Test that a BA connected to itself is allowed if not explicitly reversed."""
        csv_content = CSV_HEADER + "BA1,N1,BA1,N2,100.0\n"  # Intertie within BA1
        temp_csv_path = self._create_temp_csv_file(csv_content)
        params = PowerTradeParams.from_csv(temp_csv_path)

        self.assertCountEqual(params.connected_ba, [("BA1", "BA1")])
        self.assertEqual(params.total_transfer_limits, {("BA1", "BA1"): 100.0})
        # No error should be raised by __post_init__ for connected_ba


if __name__ == "__main__":
    unittest.main(argv=["first-arg-is-ignored"], exit=False)
