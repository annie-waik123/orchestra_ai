import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Resolve Database URL (PostgreSQL in production/Docker, SQLite for fallback)
DATABASE_URL = os.getenv("ORCHESTRA_DATABASE_URL")

if not DATABASE_URL:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    storage_dir = os.getenv(
        "ORCHESTRA_STORAGE_DIR", 
        os.path.join(project_root, "brain", "storage")
    )
    # Ensure storage directory exists
    os.makedirs(storage_dir, exist_ok=True)
    db_path = os.path.join(storage_dir, "orchestra.db")
    DATABASE_URL = f"sqlite:///{db_path.replace('\\', '/')}"

# SQLite requires check_same_thread=False for multithreading
is_sqlite = DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}

from sqlalchemy.pool import NullPool
poolclass = NullPool if is_sqlite else None

engine = create_engine(
    DATABASE_URL, 
    connect_args=connect_args,
    pool_pre_ping=True,  # Automatically checks connections before querying
    poolclass=poolclass
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """FastAPI path dependency helper for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
