import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings

# Create the database directory if it doesn't already exist
os.makedirs("database", exist_ok=True)

# Create the database engine — this is the single connection to our SQLite file.
# check_same_thread=False is required by SQLite when used with FastAPI's async workers.
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=settings.DEBUG,  # Prints all SQL queries to the console when DEBUG=True
)

# SessionLocal is a factory: calling SessionLocal() opens a new database session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# All SQLAlchemy models must inherit from this Base class so SQLAlchemy
# knows which classes represent database tables
class Base(DeclarativeBase):
    pass


def get_db():
    """
    FastAPI dependency that provides a database session for each request.

    Usage in a route:
        @router.get("/example")
        def my_route(db: Session = Depends(get_db)):
            ...

    The session is automatically closed after the request finishes,
    even if an error occurred (guaranteed by the finally block).
    """
    db = SessionLocal()
    try:
        yield db  # FastAPI injects this db object into the route function
    finally:
        db.close()


def ensure_startup_migrations():
    """Apply tiny idempotent SQLite migrations that create_all cannot cover."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    with engine.begin() as conn:
        columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(holdings)")).fetchall()
        }
        if "hold_class" not in columns:
            conn.execute(
                text(
                    "ALTER TABLE holdings "
                    "ADD COLUMN hold_class VARCHAR(20) NOT NULL DEFAULT 'auto'"
                )
            )
