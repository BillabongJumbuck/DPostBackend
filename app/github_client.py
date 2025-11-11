import os
import re
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

GITHUB_API_BASE = "https://api.github.com"


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
	ssh_match = re.match(r"^git@github\\.com:(?P<owner>[\\w.-]+)/(?P<repo>[\\w.-]+)(?:\\.git)?$", url)
	if ssh_match:
		return ssh_match.group("owner"), ssh_match.group("repo")

	http_match = re.match(
		r"^https?://github\\.com/(?P<owner>[\\w.-]+)/(?P<repo>[\\w.-]+)(?:\\.git)?/?$", url
	)
	if http_match:
		return http_match.group("owner"), http_match.group("repo")

	return None


async def fork_repository(repo_url: str, org: Optional[str] = None, timeout_seconds: float = 15.0) -> dict:
	"""
	Trigger a fork on GitHub. If 'org' provided, fork into that organization, else into the authenticated user.
	Returns the GitHub API response JSON.
	"""
	parsed = parse_repo_url(repo_url)
	if not parsed:
		raise ValueError("Invalid GitHub repository URL")
	owner, repo = parsed

	pat = get_github_pat()
	headers = {
		"Accept": "application/vnd.github+json",
		"Authorization": f"Bearer {pat}",
		"X-GitHub-Api-Version": "2022-11-28",
	}

	payload = {}
	if org:
		payload["organization"] = org

	url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/forks"

	async with httpx.AsyncClient(timeout=timeout_seconds) as client:
		response = await client.post(url, headers=headers, json=payload or None)
		if response.status_code >= 400:
			# Surface useful error information
			try:
				err_json = response.json()
			except Exception:
				err_json = {"message": response.text}
			raise httpx.HTTPStatusError(
				message=f"GitHub API error {response.status_code}: {err_json.get('message')}",
				request=response.request,
				response=response,
			)
		return response.json()


