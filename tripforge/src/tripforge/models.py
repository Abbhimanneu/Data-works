from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Kind = Literal["sight", "food", "nature", "activity", "shopping", "nightlife", "other"]
Mode = Literal["flight", "train", "bus", "car", "boat", "cruise", "none"]


class City(BaseModel):
    name: str
    nights: int = Field(ge=0, le=30)
    arrive_by: Mode = "none"  # how you get here from the previous city


class Place(BaseModel):
    name: str
    city: str
    kind: Kind = "sight"
    must: bool = False
    hours: float = Field(default=2.0, gt=0, le=12)


class TripBrief(BaseModel):
    country: str
    days: int = Field(ge=1, le=60)
    travelers: int = Field(default=1, ge=1, le=20)
    budget_inr: int | None = Field(default=None, ge=0)
    pace: Literal["slow", "normal", "fast"] = "normal"
    tier: Literal["budget", "mid", "comfort"] = "mid"
    interests: list[str] = []
    cities: list[City]
    places: list[Place]

    @field_validator("cities")
    @classmethod
    def at_least_one_city(cls, v: list[City]) -> list[City]:
        if not v:
            raise ValueError("brief needs at least one city")
        return v


class GeoPoint(BaseModel):
    query: str
    lat: float
    lon: float
    display_name: str
    source: str


class Stop(BaseModel):
    day: int
    date: date | None
    city: str
    seq: int
    place: str
    kind: str
    hours: float
    lat: float
    lon: float
    km_from_prev: float


class CostLine(BaseModel):
    day: int | None
    category: str
    item: str
    amount_inr: float
    basis: str  # how it was computed, shown in the PDF
