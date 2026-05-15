# Khởi tạo SQLAlchemy async engine và session factory
# Cung cấp "get_db()" để FastAPI inject session vào endpoint qua Depends()

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine 
from sqlalchemy.orm import DeclarativeBase

from core.config import DATABASE_URL

# pool_recycle: làm mới connection mỗi 1h (tránh MySQL tự ngắt connection cũ)
# pool_pre_ping: ping trước khi dùng để đảm bảo connection còn sống
engine = create_async_engine(DATABASE_URL, pool_recycle=3600, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


# Class cha cho mọi ORM model. Subclass nó trong core/models.py
class Base(DeclarativeBase):
    pass

# Tạo các bảng (nếu chưa có) khi app khởi động
async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# Yield 1 DB session cho mỗi HTTP request, tự động đóng khi xong
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
