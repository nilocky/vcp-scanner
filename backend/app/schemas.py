from pydantic import BaseModel, Field


class Filters(BaseModel):
    min_contractions: int = Field(default=3, ge=1)
    min_tightness: float = Field(default=8.0, gt=0)
    min_ai_score: int = Field(default=0, ge=0, le=100)
    include_premature: bool = False


class SavedScan(BaseModel):
    id: int
    name: str
    filters: Filters
    created_at: int


class SavedScanCreate(BaseModel):
    name: str
    filters: Filters
