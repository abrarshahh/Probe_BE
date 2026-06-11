import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

from app.config import settings

logger = logging.getLogger(__name__)

db_url = settings.database_url
# Ensure we're using asyncpg
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    db_url,
    echo=False,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()

async def get_db():
    """FastAPI dependency for getting a database session."""
    logger.debug("Yielding database session from AsyncSessionLocal")
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            logger.debug("Closing database session")

async def init_db() -> None:
    """Create all tables in the database."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("PostgreSQL tables created.")
