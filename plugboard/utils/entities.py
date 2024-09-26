"""Provides utility functions for working with entity ids."""

from plugboard.schemas.entities import Entity
from plugboard.utils import gen_rand_str


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
    def job_id(cls) -> str:
        """Returns a unique job id.

        Returns:
            str: The generated job id.
        """
        return cls.id(Entity.Job)
