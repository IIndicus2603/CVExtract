# SQLAlchemy async engine + session factory, get_db() inject vào FastAPI endpoint

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.config import DATABASE_URL

# pool_recycle=3600, làm mới connection mỗi 1h tránh MySQL ngắt connection cũ
engine = create_async_engine(DATABASE_URL, pool_recycle=3600, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """Tạo các bảng (nếu chưa có) khi app khởi động"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """Yield 1 DB session cho mỗi HTTP request"""
    async with AsyncSessionLocal() as session:
        yield session
