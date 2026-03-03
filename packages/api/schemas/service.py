"""Service schema definitions."""

from pydantic import BaseModel


class ServiceSchema(BaseModel):
    """Serialized service profile."""

    slug: str
    name: str
    category: str
    description: str | None = None
