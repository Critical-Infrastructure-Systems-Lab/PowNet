"""test_folder_utils.py"""

import unittest
import pathlib
from unittest import mock

from pownet import folder_utils


class TestFolderUtils(unittest.TestCase):

    def test_get_pownet_dir(self):
        # Path to the actual folder_utils.py file
        utils_file_path = pathlib.Path(folder_utils.__file__).resolve()
        # Expected: three levels up from folder_utils.py
        # .../utils/ -> .../pownet/ -> .../src/
        expected_dir = utils_file_path.parent.parent.parent

        self.assertEqual(pathlib.Path(folder_utils.get_pownet_dir()), expected_dir)
        self.assertTrue(expected_dir.is_dir())

    def test_get_home_dir(self):
        with mock.patch(
            "os.path.expanduser", return_value="/mocked/home/user"
        ) as mocked_expanduser:
            self.assertEqual(folder_utils.get_home_dir(), "/mocked/home/user")
            mocked_expanduser.assert_called_once_with("~")

    def test_get_database_dir(self):
        utils_file_path = pathlib.Path(folder_utils.__file__).resolve()
        # Expected: .../utils/database/
        expected_dir = utils_file_path.parent / "database"

        self.assertEqual(pathlib.Path(folder_utils.get_database_dir()), expected_dir)
        self.assertTrue(expected_dir.is_dir())

    def test_get_test_dir(self):
        # Scenario 1: Using the actual get_pownet_dir
        pownet_dir_path = pathlib.Path(folder_utils.get_pownet_dir())
        # The function joins get_pownet_dir() with "src" and "test_pownet"
        expected_dir = pownet_dir_path / "src" / "test_pownet"
        self.assertEqual(pathlib.Path(folder_utils.get_test_dir()), expected_dir)

        # Scenario 2: Mocking get_pownet_dir for isolation
        with mock.patch(
            "pownet.folder_utils.get_pownet_dir",
            return_value="/fake/pownet_root_dir",
        ) as mocked_get_pownet:
            expected_dir_mocked = pathlib.Path("/fake/pownet_root_dir/src/test_pownet")
            self.assertEqual(
                pathlib.Path(folder_utils.get_test_dir()), expected_dir_mocked
            )


if __name__ == "__main__":
    unittest.main()
