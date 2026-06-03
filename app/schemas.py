from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
 
 
# ── Holding Schemas ────────────────────────────────────────────────────
 
 #Model to create a new holding, with required fields for ticker and shares, and optional fields for average cost and notes. The ticker field is automatically converted to uppercase and stripped of whitespace, and the shares and avg_cost fields must be greater than 0 if provided. The notes field has a maximum length of 500 characters.
class HoldingCreate(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10,
                        description="Stock ticker symbol, e.g. VOO")
    shares: float = Field(..., gt=0, description="Number of shares (must be > 0)")
    avg_cost: Optional[float] = Field(None, gt=0, description="Average purchase price")
    notes: Optional[str] = Field(None, max_length=500)
 
    # Validator: automatically uppercase the ticker
    @field_validator("ticker")
    @classmethod
    def uppercase_ticker(cls, v):
        return v.upper().strip()
 
 
 #Model to input data when updating an existing holding, with optional fields for shares, avg_cost, notes, and is_active status. The shares and avg_cost fields must be greater than 0 if provided, and the notes field has a maximum length of 500 characters.
class HoldingUpdate(BaseModel):
    shares: Optional[float] = Field(None, gt=0)
    avg_cost: Optional[float] = Field(None, gt=0)
    notes: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None
 
 
 #Model to return holding data in API responses, with fields for id, ticker, company name, shares, average cost, active status, notes, and the date the holding was added. The Config class allows this model to be populated from SQLAlchemy model attributes.
class HoldingResponse(BaseModel):
    id: int
    ticker: str
    company_name: Optional[str]
    shares: float
    avg_cost: Optional[float]
    is_active: bool
    notes: Optional[str]
    added_at: datetime
 
    class Config:
        from_attributes = True  # Allows reading from SQLAlchemy model attributes
 
 
# ── Portfolio Schemas ──────────────────────────────────────────────────
 
class PortfolioCreate(BaseModel):
    name: str = Field(default="My Portfolio", max_length=100)
    description: Optional[str] = None
 
 
class PortfolioResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: datetime
    holdings: list[HoldingResponse] = []
 
    class Config:
        from_attributes = True
