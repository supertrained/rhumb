"""Failure mode schema definitions."""

from pydantic import BaseModel


class FailureModeSchema(BaseModel):
    """Serialized failure mode payload."""

    category: str
    title: str
    severity: str
    description: str
