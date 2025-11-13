import asyncio
import json
from typing import Any, Optional

from sqlalchemy import select

from .database import SessionLocal
from .models import RepositoryCache


async def get_cached_response(repo_full_name: str, org: Optional[str]) -> Optional[dict[str, Any]]:
	def _get() -> Optional[dict[str, Any]]:
		with SessionLocal() as session:
			statement = select(RepositoryCache).where(
				RepositoryCache.repo_full_name == repo_full_name, RepositoryCache.org == org
			)
			result = session.execute(statement).scalar_one_or_none()
			if not result:
				return None
			return json.loads(result.response_json)

	return await asyncio.to_thread(_get)


async def upsert_cached_response(repo_full_name: str, org: Optional[str], payload: dict[str, Any]) -> None:
	data = json.dumps(payload)

	def _upsert() -> None:
		with SessionLocal() as session:
			statement = select(RepositoryCache).where(
				RepositoryCache.repo_full_name == repo_full_name, RepositoryCache.org == org
			)
			entry = session.execute(statement).scalar_one_or_none()
			if entry:
				entry.response_json = data
			else:
				entry = RepositoryCache(repo_full_name=repo_full_name, org=org, response_json=data)
				session.add(entry)
			session.commit()

	await asyncio.to_thread(_upsert)


async def repository_exists(repo_full_name: str, org: Optional[str]) -> bool:
	"""Check if a repository exists in the cache database."""
	def _check() -> bool:
		with SessionLocal() as session:
			statement = select(RepositoryCache).where(
				RepositoryCache.repo_full_name == repo_full_name, RepositoryCache.org == org
			)
			result = session.execute(statement).scalar_one_or_none()
			return result is not None

	return await asyncio.to_thread(_check)


async def delete_cached_response(repo_full_name: str, org: Optional[str]) -> bool:
	"""Delete a repository cache entry from the database. Returns True if deleted, False if not found."""
	def _delete() -> bool:
		with SessionLocal() as session:
			statement = select(RepositoryCache).where(
				RepositoryCache.repo_full_name == repo_full_name, RepositoryCache.org == org
			)
			entry = session.execute(statement).scalar_one_or_none()
			if not entry:
				return False
			session.delete(entry)
			session.commit()
			return True

	return await asyncio.to_thread(_delete)