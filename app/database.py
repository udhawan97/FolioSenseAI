from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings
import os

# checking for the database file and creating it if it doesn't exist
os.makedirs("database", exist_ok=True)

# Connecting to SQLite database
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=settings.DEBUG,
)

# Creating a sessionnaker for database interactions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Base class for our database models
class Base(DeclarativeBase):
    pass


# Defining a dependency to get a database session for each request
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
