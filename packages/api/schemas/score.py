"""Score schema definitions."""

from pydantic import BaseModel


class ANScoreSchema(BaseModel):
    """Serialized AN score payload."""

    score: float
    confidence: float
    tier: str
    explanation: str
