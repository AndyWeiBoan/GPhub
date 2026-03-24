from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

# SQLite needs check_same_thread=False via connect_args; PostgreSQL ignores it
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=not _is_sqlite,  # pool_pre_ping not supported by aiosqlite
    connect_args=_connect_args,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
