"""Test that bellbird's package version is 0.11.0."""

import bellbird


def test_version_is_0_11_0():
    """GIVEN the bellbird package
    WHEN __version__ is read
    THEN it equals '0.11.0'."""
    assert bellbird.__version__ == "0.11.0"
