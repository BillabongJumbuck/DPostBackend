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


async def get_file_content(
	fork_owner: str,
	repo: str,
	path: str,
	branch: str = "main",
	timeout_seconds: float = 15.0,
) -> dict | None:
	"""
	Get file content from GitHub repository.
	Returns the file content dict with 'sha' and 'content' (base64 encoded), or None if file doesn't exist.
	"""
	logger.info("Get file request: fork_owner=%s, repo=%s, path=%s, branch=%s", fork_owner, repo, path, branch)

	pat = get_github_pat()
	headers = {
		"Accept": "application/vnd.github+json",
		"Authorization": f"Bearer {pat}",
		"X-GitHub-Api-Version": "2022-11-28",
		"User-Agent": "DPostBackend/0.1 (+fastapi; httpx)",
	}

	url = f"{GITHUB_API_BASE}/repos/{fork_owner}/{repo}/contents/{path}"
	params = {"ref": branch}

	async with httpx.AsyncClient(timeout=timeout_seconds) as client:
		response = await client.get(url, headers=headers, params=params)
		logger.info("GitHub response: status=%s", response.status_code)
		if response.status_code == 404:
			# File doesn't exist, return None
			return None
		if response.status_code >= 400:
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
		return response.json()


async def create_or_update_file(
	fork_owner: str,
	repo: str,
	path: str,
	content: str,
	message: str,
	branch: str = "main",
	timeout_seconds: float = 15.0,
) -> dict:
	"""
	Create or update a file in GitHub repository.
	If file exists, it will be updated. If not, it will be created.
	Returns the GitHub API response JSON.
	"""
	logger.info("Create/update file request: fork_owner=%s, repo=%s, path=%s", fork_owner, repo, path)

	pat = get_github_pat()
	headers = {
		"Accept": "application/vnd.github+json",
		"Authorization": f"Bearer {pat}",
		"X-GitHub-Api-Version": "2022-11-28",
		"User-Agent": "DPostBackend/0.1 (+fastapi; httpx)",
	}

	# Check if file exists to get its SHA
	existing_file = await get_file_content(fork_owner, repo, path, branch, timeout_seconds)

	import base64

	# Encode content to base64
	content_bytes = content.encode("utf-8")
	content_base64 = base64.b64encode(content_bytes).decode("utf-8")

	payload = {
		"message": message,
		"content": content_base64,
		"branch": branch,
	}

	# If file exists, include SHA for update
	if existing_file and "sha" in existing_file:
		payload["sha"] = existing_file["sha"]
		logger.debug("Updating existing file with SHA: %s", existing_file["sha"][:8])
	else:
		logger.debug("Creating new file")

	url = f"{GITHUB_API_BASE}/repos/{fork_owner}/{repo}/contents/{path}"

	async with httpx.AsyncClient(timeout=timeout_seconds) as client:
		response = await client.put(url, headers=headers, json=payload)
		logger.info("GitHub response: status=%s", response.status_code)
		if response.status_code >= 400:
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
		return response.json()


async def trigger_workflow(
	fork_owner: str,
	repo: str,
	workflow_id: str = "api-test.yml",
	branch: str = "main",
	timeout_seconds: float = 15.0,
) -> dict:
	"""
	Trigger a GitHub Actions workflow using workflow_dispatch.
	
	Args:
		fork_owner: The owner of the forked repository
		repo: The repository name
		workflow_id: The workflow file name (e.g., "api-test.yml") or workflow ID
		branch: The branch to run the workflow on
		timeout_seconds: Request timeout
	
	Returns:
		GitHub API response JSON
	"""
	logger.info("Trigger workflow request: fork_owner=%s, repo=%s, workflow_id=%s, branch=%s", fork_owner, repo, workflow_id, branch)

	pat = get_github_pat()
	headers = {
		"Accept": "application/vnd.github+json",
		"Authorization": f"Bearer {pat}",
		"X-GitHub-Api-Version": "2022-11-28",
		"User-Agent": "DPostBackend/0.1 (+fastapi; httpx)",
	}

	# First, get the workflow ID by file name
	# List workflows to find the one we want
	workflows_url = f"{GITHUB_API_BASE}/repos/{fork_owner}/{repo}/actions/workflows"
	
	async with httpx.AsyncClient(timeout=timeout_seconds) as client:
		# Get list of workflows
		workflows_response = await client.get(workflows_url, headers=headers)
		if workflows_response.status_code >= 400:
			try:
				err_json = workflows_response.json()
			except Exception:
				err_json = {"message": workflows_response.text}
			logger.error("GitHub API error %s: %s", workflows_response.status_code, err_json)
			raise httpx.HTTPStatusError(
				message=f"GitHub API error {workflows_response.status_code}: {err_json.get('message', 'Unknown error')}",
				request=workflows_response.request,
				response=workflows_response,
			)
		
		workflows_data = workflows_response.json()
		workflows = workflows_data.get("workflows", [])
		
		# Find workflow by name
		workflow_id_num = None
		for workflow in workflows:
			if workflow.get("path") == f".github/workflows/{workflow_id}" or workflow.get("name") == workflow_id:
				workflow_id_num = workflow.get("id")
				break
		
		if not workflow_id_num:
			# If not found by name, try using the workflow_id directly as numeric ID
			logger.warning("Workflow %s not found by name, trying as ID", workflow_id)
			try:
				workflow_id_num = int(workflow_id)
			except ValueError:
				raise ValueError(f"Workflow '{workflow_id}' not found and is not a valid workflow ID")

		# Trigger the workflow
		trigger_url = f"{GITHUB_API_BASE}/repos/{fork_owner}/{repo}/actions/workflows/{workflow_id_num}/dispatches"
		payload = {
			"ref": branch,
		}
		
		trigger_response = await client.post(trigger_url, headers=headers, json=payload)
		logger.info("GitHub workflow trigger response: status=%s", trigger_response.status_code)
		
		if trigger_response.status_code == 204:
			# 204 No Content is the expected success response
			logger.info("Workflow triggered successfully")
			return {"status": "triggered", "workflow_id": workflow_id_num}
		
		if trigger_response.status_code >= 400:
			try:
				err_json = trigger_response.json()
			except Exception:
				err_json = {"message": trigger_response.text}
			logger.error("GitHub API error %s: %s", trigger_response.status_code, err_json)
			raise httpx.HTTPStatusError(
				message=f"GitHub API error {trigger_response.status_code}: {err_json.get('message', 'Unknown error')}",
				request=trigger_response.request,
				response=trigger_response,
			)
		
		# Unexpected status code
		logger.warning("Unexpected status code: %s", trigger_response.status_code)
		return {"status": "unknown", "status_code": trigger_response.status_code}


async def merge_upstream(
    fork_owner: str,
    repo: str,
    branch: str = "main",
    timeout_seconds: float = 15.0,
) -> dict:
    """
    Trigger GitHub's 'Merge upstream' operation for a forked repository.

    This calls POST /repos/{owner}/{repo}/merge-upstream with JSON {"branch": branch}.
    Returns the parsed JSON response when available, or a dict containing status information.
    Raises httpx.HTTPStatusError on 4xx/5xx responses.
    """
    logger.info("Merge upstream request: fork_owner=%s, repo=%s, branch=%s", fork_owner, repo, branch)

    pat = get_github_pat()
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {pat}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "DPostBackend/0.1 (+fastapi; httpx)",
    }

    url = f"{GITHUB_API_BASE}/repos/{fork_owner}/{repo}/merge-upstream"
    payload = {"branch": branch}

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.post(url, headers=headers, json=payload)
        logger.info("GitHub merge-upstream response: status=%s", response.status_code)
        # 200 OK or 202 Accepted are expected
        if response.status_code >= 400:
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

        # Try to return JSON if present, otherwise return status info
        try:
            return response.json()
        except Exception:
            return {"status_code": response.status_code, "content": response.text}