import logging
import os
import re
from typing import Optional

import httpx
from dotenv import load_dotenv

from .cache import get_cached_response, upsert_cached_response

load_dotenv()

GITHUB_API_BASE = "https://api.github.com"
logger = logging.getLogger("app.github_client")


def get_github_pat() -> str:
	pat = os.getenv("GITHUB_PAT") or ""
	if not pat:
		raise RuntimeError("GITHUB_PAT not configured. Please set it in .env")
	return pat


def parse_repo_url(repo_url: str) -> Optional[tuple[str, str]]:
	"""
	Support forms:
	- https://github.com/{owner}/{repo}
	- http://github.com/{owner}/{repo}
	- git@github.com:{owner}/{repo}.git
	- https://github.com/{owner}/{repo}.git
	Returns (owner, repo) or None if not matched.
	"""
	url = repo_url.strip()
	# SSH form
	ssh_match = re.match(r"^git@github\.com:(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)(?:\.git)?$", url)
	if ssh_match:
		owner = ssh_match.group("owner")
		repo = ssh_match.group("repo")
		if repo.lower().endswith(".git"):
			repo = repo[:-4]
		return owner, repo

	# HTTP/HTTPS form
	http_match = re.match(r"^https?://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)(?:\.git)?/?$", url)
	if http_match:
		owner = http_match.group("owner")
		repo = http_match.group("repo")
		if repo.lower().endswith(".git"):
			repo = repo[:-4]
		return owner, repo

	logger.debug("Failed to parse repository URL: %s", repo_url)
	return None


async def fork_repository(
	repo_url: str,
	org: Optional[str] = None,
	timeout_seconds: float = 15.0,
	use_cache: bool = True,
) -> dict:
	"""
	Trigger a fork on GitHub. If 'org' provided, fork into that organization, else into the authenticated user.
	Returns the GitHub API response JSON.
	"""
	logger.info("Fork request: repo_url=%s, org=%s", repo_url, org)
	repo_url = str(repo_url).strip()
	org = str(org).strip() if org else None
	parsed = parse_repo_url(repo_url)
	if not parsed:
		raise ValueError("Invalid GitHub repository URL")
	owner, repo = parsed
	logger.debug("Parsed repo: owner=%s, repo=%s", owner, repo)

	repo_full_name = f"{owner}/{repo}"

	if use_cache:
		cached = await get_cached_response(repo_full_name, org)
		if cached is not None:
			logger.info("Cache hit for repo=%s org=%s", repo_full_name, org)
			return cached

	pat = get_github_pat()
	headers = {
		"Accept": "application/vnd.github+json",
		"Authorization": f"Bearer {pat}",
		"X-GitHub-Api-Version": "2022-11-28",
		"User-Agent": "DPostBackend/0.1 (+fastapi; httpx)",
	}

	payload = {}
	if org:
		payload["organization"] = org

	url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/forks"
	logger.debug("POST %s payload=%s", url, payload or None)

	async with httpx.AsyncClient(timeout=timeout_seconds) as client:
		response = await client.post(url, headers=headers, json=payload or None)
		logger.info("GitHub response: status=%s", response.status_code)
		if response.status_code >= 400:
			# Surface useful error information
			try:
				err_json = response.json()
			except Exception:
				err_json = {"message": response.text}
			logger.error("GitHub API error %s: %s", response.status_code, err_json)
			raise httpx.HTTPStatusError(
				message=f"GitHub API error {response.status_code}: {err_json.get('message')}",
				request=response.request,
				response=response,
			)
		try:
			body = response.json()
		except Exception:
			body = {"message": "<non-json-response>"}
		logger.debug("GitHub success body received")

		if use_cache:
			await upsert_cached_response(repo_full_name, org, body)
		return body


async def delete_repository(
	fork_owner: str,
	repo: str,
	timeout_seconds: float = 15.0,
) -> None:
	"""
	Delete a forked repository on GitHub.
	Args:
		fork_owner: The owner of the forked repository (user or org)
		repo: The repository name
	"""
	logger.info("Delete repository request: fork_owner=%s, repo=%s", fork_owner, repo)

	pat = get_github_pat()
	headers = {
		"Accept": "application/vnd.github+json",
		"Authorization": f"Bearer {pat}",
		"X-GitHub-Api-Version": "2022-11-28",
		"User-Agent": "DPostBackend/0.1 (+fastapi; httpx)",
	}

	url = f"{GITHUB_API_BASE}/repos/{fork_owner}/{repo}"
	logger.debug("DELETE %s", url)

	async with httpx.AsyncClient(timeout=timeout_seconds) as client:
		response = await client.delete(url, headers=headers)
		logger.info("GitHub response: status=%s", response.status_code)
		# 204 No Content is the expected success response for delete
		if response.status_code == 204:
			logger.info("Repository deleted successfully")
			return
		# Handle error status codes
		if response.status_code >= 400:
			# Surface useful error information
			try:
				err_json = response.json()
			except Exception:
				err_json = {"message": response.text}
			logger.error("GitHub API error %s: %s", response.status_code, err_json)
			raise httpx.HTTPStatusError(
				message=f"GitHub API error {response.status_code}: {err_json.get('message', 'Unknown error')}",
				request=response.request,
				response=response,
			)
		# Unexpected status code (not 204 and not error)
		logger.warning("Unexpected status code: %s", response.status_code)