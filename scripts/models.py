"""Shared Pydantic models for scripts."""
from datetime import date
from uuid import UUID

from pydantic import BaseModel


class SeedResult(BaseModel):
    topic_ids: list[UUID]
    nl_ids: dict[str, UUID]
    start: date
