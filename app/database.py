import asyncio
import os
from pathlib import Path
from typing import AsyncIterator, Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


def _build_sqlite_path(db_url: str) -> None:
	"""
	Ensure directory exists if we are using a filesystem SQLite URL like sqlite:///./data/cache.db
	"""
	if db_url.startswith("sqlite:///"):
		path = db_url.replace("sqlite:///", "", 1)
		if path.startswith("./"):
			path = path[2:]
		db_path = Path(path)
		if db_path.parent:
			db_path.parent.mkdir(parents=True, exist_ok=True)


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/cache.db")
_build_sqlite_path(DATABASE_URL)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_session() -> Iterator[Session]:
	session = SessionLocal()
	try:
		yield session
	finally:
		session.close()


async def init_db() -> None:
	"""
	Run metadata creation in a thread to avoid blocking the event loop.
	"""

	def _create_all() -> None:
		Base.metadata.create_all(bind=engine)

	await asyncio.to_thread(_create_all)


