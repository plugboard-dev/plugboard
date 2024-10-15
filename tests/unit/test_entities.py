"""Tests for the EntityIdGen class."""

import re

import pytest

from plugboard.schemas.entities import Entity
from plugboard.utils.entities import EntityIdGen


def test_entity_id_gen_id() -> None:
    """Tests the `id` method of EntityIdGen."""
    generated_id = EntityIdGen.id(Entity.Job)
    assert generated_id.startswith(Entity.Job.id_prefix)
    assert re.match(Entity.Job.id_regex, generated_id) is not None


def test_entity_id_gen_parse() -> None:
    """Tests the `parse` method of EntityIdGen."""
    entity_id = "Job_12345678"
    parsed_entity, parsed_id = EntityIdGen.parse(entity_id)
    assert parsed_entity == Entity.Job
    assert parsed_id == "12345678"


def test_entity_id_gen_job_id() -> None:
    """Tests the `job_id` method of EntityIdGen."""
    generated_job_id = EntityIdGen.job_id()
    assert generated_job_id.startswith(Entity.Job.id_prefix)
    assert re.match(Entity.Job.id_regex, generated_job_id) is not None


@pytest.mark.parametrize(
    "id_str, is_job",
    [
        ("Job_12345678", True),
        ("User_12345678", False),
        ("12345678", False),
    ],
)
def test_entity_id_gen_is_job_id(id_str: str, is_job: bool) -> None:
    """Tests the `is_job_id` method of EntityIdGen."""
    assert EntityIdGen.is_job_id(id_str) is is_job
