"""Tests for the `utils.random` module."""

from plugboard.utils.random import RANDOM_CHAR_COUNT, RANDOM_CHAR_SET, gen_rand_str


def test_gen_rand_str() -> None:
    """Tests the `gen_rand_str` function."""
    random_string = gen_rand_str()
    assert isinstance(random_string, str)
    assert len(random_string) == RANDOM_CHAR_COUNT
    assert all(char in RANDOM_CHAR_SET for char in random_string)
