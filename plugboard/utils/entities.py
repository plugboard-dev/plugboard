"""Provides utility functions for working with entity ids."""

import re

from plugboard.schemas.entities import ENTITY_ID_REGEX, Entity
from plugboard.utils.random import gen_rand_str


class EntityIdGen:
    """EntityIdGen generates entity ids."""

    @classmethod
    def id(cls, entity: Entity) -> str:
        """Returns a unique entity id.

        Args:
            entity: The entity to generate an id for.

        Returns:
            str: The generated id.
        """
        return entity.id_prefix + gen_rand_str()

    @classmethod
    def parse(cls, id: str) -> tuple[Entity, str]:
        """Parses an entity id.

        Args:
            id: The entity id to parse.

        Returns:
            tuple[Entity, str]: The parsed entity and id.
        """
        parsed = re.match(ENTITY_ID_REGEX, id)
        if parsed is not None:
            try:
                entity = Entity[parsed.group("entity")]
                entity_id = parsed.group("id")
            except (IndexError, KeyError):
                pass
            else:
                return entity, entity_id
        raise ValueError(f"Invalid entity id: {id}")

    @classmethod
    def job_id(cls) -> str:
        """Returns a unique job id.

        Returns:
            str: The generated job id.
        """
        return cls.id(Entity.Job)

    @classmethod
    def is_job_id(cls, id: str) -> bool:
        """Checks if an id is a job id.

        Args:
            id: The id to check.

        Returns:
            bool: True if the id is a job id.
        """
        return re.match(Entity.Job.id_regex, id) is not None
