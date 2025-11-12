from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class RepositoryCache(Base):
	__tablename__ = "repository_cache"
	__table_args__ = (UniqueConstraint("repo_full_name", "org", name="uq_repository_org"),)

	id = Column(Integer, primary_key=True, autoincrement=True)
	repo_full_name = Column(String(512), nullable=False)
	org = Column(String(255), nullable=True)
	response_json = Column(Text, nullable=False)
	created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
	updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

	def __repr__(self) -> str:  # pragma: no cover - helpful for debugging
		return f"<RepositoryCache repo_full_name={self.repo_full_name!r} org={self.org!r}>"


