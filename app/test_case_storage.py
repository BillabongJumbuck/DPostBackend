import asyncio
import json
from pathlib import Path
from typing import Any

import logging

logger = logging.getLogger("app.test_case_storage")

# Default directory for storing test case files
TEST_CASES_DIR = Path("./data/test_cases")
TEST_CASES_DIR.mkdir(parents=True, exist_ok=True)


def _generate_filename(owner: str, repo: str, org: str | None) -> str:
	"""
	Generate a filename based on repository owner, repo name, and optional org.
	Format: {owner}_{repo}_{org}.json or {owner}_{repo}.json if org is None
	"""
	safe_owner = owner.replace("/", "_").replace("\\", "_")
	safe_repo = repo.replace("/", "_").replace("\\", "_")
	if org:
		safe_org = org.replace("/", "_").replace("\\", "_")
		return f"{safe_owner}_{safe_repo}_{safe_org}.json"
	return f"{safe_owner}_{safe_repo}.json"


async def save_test_case(
	owner: str, repo: str, org: str | None, test_case_json: dict[str, Any]
) -> str:
	"""
	Save OpenAPI test case JSON to file system.
	Returns the file path where the test case was saved.
	"""
	filename = _generate_filename(owner, repo, org)
	file_path = TEST_CASES_DIR / filename

	def _save() -> str:
		# Ensure directory exists
		file_path.parent.mkdir(parents=True, exist_ok=True)
		# Write JSON file (overwrite if exists)
		with open(file_path, "w", encoding="utf-8") as f:
			json.dump(test_case_json, f, indent=2, ensure_ascii=False)
		logger.info("Test case saved to: %s", file_path)
		return str(file_path)

	return await asyncio.to_thread(_save)


async def load_test_case(owner: str, repo: str, org: str | None) -> dict[str, Any] | None:
	"""
	Load OpenAPI test case JSON from file system.
	Returns the JSON content or None if file doesn't exist.
	"""
	filename = _generate_filename(owner, repo, org)
	file_path = TEST_CASES_DIR / filename

	def _load() -> dict[str, Any] | None:
		if not file_path.exists():
			return None
		with open(file_path, "r", encoding="utf-8") as f:
			return json.load(f)

	return await asyncio.to_thread(_load)


async def test_case_exists(owner: str, repo: str, org: str | None) -> bool:
	"""
	Check if a test case file exists for the given repository.
	"""
	filename = _generate_filename(owner, repo, org)
	file_path = TEST_CASES_DIR / filename

	def _check() -> bool:
		return file_path.exists()

	return await asyncio.to_thread(_check)


async def delete_test_case(owner: str, repo: str, org: str | None) -> bool:
	"""
	Delete OpenAPI test case file from file system.
	Returns True if deleted, False if file doesn't exist.
	"""
	filename = _generate_filename(owner, repo, org)
	file_path = TEST_CASES_DIR / filename

	def _delete() -> bool:
		if not file_path.exists():
			return False
		file_path.unlink()
		logger.info("Test case deleted: %s", file_path)
		return True

	return await asyncio.to_thread(_delete)