"""Unit tests of the `ComponentRegistry`."""
# ruff: noqa: D101,D102,D103

import pytest

from plugboard.component import ComponentRegistry
from plugboard.exceptions import RegistryError
from tests.integration.test_process_with_components_run import A, B


def test_component_registry() -> None:
    """Tests the `ComponentRegistry`."""
    # Must load components from string name
    a = ComponentRegistry.get("tests.integration.test_process_with_components_run.A")
    isinstance(a, A)
    b = ComponentRegistry.get("tests.integration.test_process_with_components_run.B")
    isinstance(b, B)
    with pytest.raises(RegistryError):
        ComponentRegistry.get("tests.integration.test_process_with_components_run.does_not_exist")
