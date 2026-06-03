from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from datetime import datetime
 
 #Creating a class to represent the Portfolio table in the database, with columns for id, name, description, created_at, updated_at, and a relationship to the holdings in the portfolio.
class Portfolio(Base):
    __tablename__ = "portfolios"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, default="My Portfolio")
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    holdings = relationship("Holding", back_populates="portfolio", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Portfolio (self.name)>"
    
#The amount of money invested in the portfolio, calculated by summing the cost of all holdings (shares * avg_cost)
class Holding(Base):
    __tablename__ = "holdings"
        
    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    ticker = Column(String(10), nullable=False)
    company_name = Column(String(200), nullable=True)
    shares = Column(Float, nullable=False, default=0.0)
    avg_cost = Column(Float, nullable=False, default=0.0)
    is_active = Column(Boolean, default=True)
    notes= Column(Text, nullable=True)
    added_at = Column(DateTime, default=func.now())
    portfolio = relationship("Portfolio", back_populates="holdings")
    price_history = relationship("PriceSnapcshot", back_populates="holding", cascade="all, delete-orphan")

#The price snapshots for a holding, which is a list of PriceSnapshot objects related to this holding. This allows us to track the historical prices of the stock over time.
class PriceSnapcshot(Base):
    __tablename__ = "price_snapshots"
            
    id = Column(Integer, primary_key=True, index=True)
    holding_id = Column(Integer, ForeignKey("holdings.id"), nullable=False)
    price = Column(Float, nullable=False)
    day_change_pct = Column(Float, nullable=True)
    recorded_at = Column(DateTime, default=func.now())

    holding = relationship("Holding", back_populates="price_history")

#Get summary from Claude for a specific stock or the entire portfolio, and store it in the database with the relevant metadata (ticker, price when generated, model used, etc.)
class AISummary(Base):
   
    __tablename__ = "ai_summaries"
 
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False, index=True)
    summary_type = Column(String(20), default="stock")  # "stock" or "portfolio"
    summary_text = Column(Text, nullable=False)
    price_when_generated = Column(Float, nullable=True)
    generated_at = Column(DateTime, default=func.now())
    model_used = Column(String(50), default="claude-3-haiku-20240307")


        

      