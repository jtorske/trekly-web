from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Terrain = Literal["easy", "moderate", "difficult", "extreme"]


class TrailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    region: str
    terrain: Terrain = Field(validation_alias="terrain_difficulty")
