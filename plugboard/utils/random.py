"""Provides utility functions for generating random strings."""

import random
import string


try:
    random.SystemRandom()
except NotImplementedError as e:
    raise RuntimeError("System does not provide a secure random number generator.") from e

RANDOM_CHAR_SET: str = string.ascii_letters + string.digits
RANDOM_CHAR_COUNT: int = 16


def gen_rand_str(chars: int = RANDOM_CHAR_COUNT) -> str:
    """Generates a random string of a fixed length and character set.

    With 16 chars in [a-zA-Z0-9], at 1000 ids/second it would take ~1000 years or
    30T ids for >= 1% chance of at least one collision. See here for details:
    https://zelark.github.io/nano-id-cc/

    Note: This function is not suitable for cryptographic purposes; it is intended to
    generate random strings for unique identifiers only.

    Returns:
        str: Random fixed length string.
    """
    return "".join(random.choices(RANDOM_CHAR_SET, k=chars))  # noqa: S311 (not intended for cryptographic purposes)
