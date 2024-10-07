"""Tests for the `utils.random` module."""

from plugboard.utils.random import RANDOM_CHAR_COUNT, RANDOM_CHAR_SET, gen_rand_str


def test_gen_rand_str() -> None:
    """Tests the `gen_rand_str` function."""
    random_string = gen_rand_str()
    assert isinstance(random_string, str)
    assert len(random_string) == RANDOM_CHAR_COUNT
    assert all(char in RANDOM_CHAR_SET for char in random_string)


def test_gen_rand_str_dist() -> None:
    """Tests the distribution of the `gen_rand_str` function."""
    # Generate a large number of random strings
    rand_strs = [gen_rand_str() for _ in range(1000000)]

    # Check randomness of the set of random strings
    # Note: This assertion checks that there are no duplicates in a large
    # sample of random strings. This is not a good test of randomness.
    assert len(set(rand_strs)) == len(rand_strs)
