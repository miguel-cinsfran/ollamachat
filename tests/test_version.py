"""Test that bellbird's package version is 0.9.0."""

import bellbird


def test_version_is_0_9_0():
    """GIVEN the bellbird package
    WHEN __version__ is read
    THEN it equals '0.9.0'."""
    assert bellbird.__version__ == "0.9.0"
