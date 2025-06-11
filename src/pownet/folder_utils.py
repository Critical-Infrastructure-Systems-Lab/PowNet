"folder_utils.py: Folder utility functions for pownet package." ""

import os


def get_pownet_dir() -> str:
    """Returns the root directory of the pownet package."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_home_dir() -> str:
    """Returns the home directory of the user. This is useful for testing purposes."""
    return os.path.expanduser("~")


def get_database_dir() -> str:
    """Returns the database directory of the pownet package."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "database")


def get_test_dir() -> str:
    """Returns the test directory of the pownet package."""
    return os.path.join(get_pownet_dir(), "src", "test_pownet")
