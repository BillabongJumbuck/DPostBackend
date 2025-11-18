import json
import logging

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from .cache import delete_cached_response, get_cached_response, repository_exists
from .database import init_db
from .github_client import create_or_update_file, fork_repository, get_file_content, parse_repo_url, trigger_workflow, merge_upstream
from .logging_config import configure_logging
from .test_case_storage import delete_test_case, load_test_case, save_test_case, test_case_exists
from .workflow_generator import generate_workflow

configure_logging()
app = FastAPI(title="DPostBackend", version="0.1.0")
logger = logging.getLogger("app.main")

# CORS for local frontend dev
app.add_middleware(
	CORSMiddleware,
	allow_origins=[
		"http://localhost:5173",
		"http://127.0.0.1:5173",
		"http://localhost:3000",
		"http://127.0.0.1:3000",
	],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event() -> None:
	await init_db()


@app.get("/health")
def health_check():
	logger.debug("health_check called")
	app_state = {"status": "ok"}
	return app_state


@app.get("/")
def read_root():
	logger.debug("read_root called")
	return {"message": "Welcome to DPostBackend (FastAPI)"}


class TestResultRequest(BaseModel):
	repo_url: str
	org: str | None = None
	workflow_run_id: str | None = None
	workflow_run_url: str | None = None
	test_results: dict


@app.post("/repos/test-results")
async def submit_test_results(payload: TestResultRequest):
	"""
	Receive test results from GitHub Actions workflow.
	"""
	logger.info(
		"POST /repos/test-results received: repo_url=%s, org=%s, workflow_run_id=%s",
		payload.repo_url,
		payload.org,
		payload.workflow_run_id,
	)

	# Parse repository URL
	parsed = parse_repo_url(payload.repo_url.strip())
	if not parsed:
		raise HTTPException(status_code=400, detail="Invalid GitHub repository URL")
	original_owner, repo = parsed
	repo_full_name = f"{original_owner}/{repo}"

	# Normalize org
	normalized_org = payload.org.strip() if payload.org and payload.org.strip() else None

	# Save test results to file
	import os
	from pathlib import Path
	from datetime import datetime

	results_dir = Path(__file__).parent.parent / "data" / "test_results"
	results_dir.mkdir(parents=True, exist_ok=True)

	# Generate filename: {owner}_{repo}_{org}_{timestamp}.json
	timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
	if normalized_org:
		filename = f"{original_owner}_{repo}_{normalized_org}_{timestamp}.json"
	else:
		filename = f"{original_owner}_{repo}_{timestamp}.json"
	
	results_file = results_dir / filename

	try:
		# Add metadata to test results
		results_with_metadata = {
			"repo_url": payload.repo_url,
			"repo_full_name": repo_full_name,
			"org": normalized_org,
			"workflow_run_id": payload.workflow_run_id,
			"workflow_run_url": payload.workflow_run_url,
			"received_at": datetime.now().isoformat(),
			"test_results": payload.test_results,
		}

		with open(results_file, "w", encoding="utf-8") as f:
			json.dump(results_with_metadata, f, indent=2, ensure_ascii=False)

		logger.info("Test results saved to: %s", results_file)

		return {
			"status": "ok",
			"message": "Test results received and saved successfully",
			"file_path": str(results_file),
			"repo_full_name": repo_full_name,
			"org": normalized_org,
		}
	except Exception as e:
		logger.error("Error saving test results: %s", e, exc_info=True)
		raise HTTPException(status_code=500, detail=f"Error saving test results: {e}")


@app.get("/repos/test-results")
async def get_test_results(
	repo_url: str = Query(..., description="GitHub repository URL (e.g., https://github.com/owner/repo)"),
	org: str | None = Query(None, description="Organization name"),
):
	"""
	Get the latest test result file for a repository.
	Returns the most recent test result JSON file matching the repository URL and optional org.
	Supports both original repository URLs and fork repository URLs.
	"""
	import os
	from pathlib import Path
	from datetime import datetime

	logger.info(
		"GET /repos/test-results received: repo_url=%s, org=%s",
		repo_url,
		org,
	)

	results_dir = Path(__file__).parent.parent / "data" / "test_results"
	
	if not results_dir.exists():
		raise HTTPException(status_code=404, detail="No test results found")

	# Parse repository URL
	parsed = parse_repo_url(repo_url.strip())
	if not parsed:
		raise HTTPException(status_code=400, detail="Invalid GitHub repository URL")
	owner, repo = parsed
	repo_full_name = f"{owner}/{repo}"

	# Normalize org
	normalized_org = org.strip() if org and org.strip() else None

	# Try to find fork information from database (in case query is for original repo)
	# This helps us find test results that were saved with fork repo name
	fork_full_name = None
	try:
		fork_info = await get_cached_response(repo_full_name, normalized_org)
		if fork_info:
			fork_full_name = fork_info.get("full_name")
			logger.debug("Found fork info: original=%s, fork=%s", repo_full_name, fork_full_name)
	except Exception as e:
		logger.debug("Could not get fork info for %s (org=%s): %s", repo_full_name, normalized_org, e)

	# Get all test result files, sorted by modification time (newest first)
	all_files = sorted(results_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
	
	# Find the latest matching file
	for file_path in all_files:
		filename = file_path.name
		
		# Read file and check if it matches
		try:
			with open(file_path, "r", encoding="utf-8") as f:
				file_data = json.load(f)
			
			# Extract repository info from file data
			file_repo_full_name = file_data.get("repo_full_name", "")
			file_org = file_data.get("org")
			
			# Parse repo_full_name to get owner and repo
			if not file_repo_full_name:
				continue
			
			parts = file_repo_full_name.split("/")
			if len(parts) != 2:
				continue
			
			file_owner = parts[0]
			file_repo = parts[1]
			
			# Check if it matches the query (either original repo or fork repo)
			matches_repo = False
			if file_owner == owner and file_repo == repo:
				# Direct match (query is for fork repo or same repo)
				matches_repo = True
			elif fork_full_name and file_repo_full_name == fork_full_name:
				# Match via fork mapping (query is for original repo, file has fork repo)
				matches_repo = True
			
			if not matches_repo:
				continue
			
			# Check org match
			if normalized_org is not None:
				if normalized_org and file_org != normalized_org:
					continue
				if not normalized_org and file_org is not None:
					continue
			else:
				# If org not specified, prefer files without org, but also accept files with org
				pass
			
			# Found matching file, return it
			return {
				"status": "ok",
				"filename": filename,
				"data": file_data,
			}
		except Exception as e:
			logger.warning("Error reading test result file %s: %s", filename, e)
			continue

	# No matching file found
	raise HTTPException(
		status_code=404,
		detail=f"No test results found for repository {owner}/{repo}" + (f" (org={normalized_org})" if normalized_org else "")
	)


@app.get("/repos/test-results/{filename}")
async def get_test_result_file(filename: str):
	"""
	Get a specific test result file by filename.
	"""
	import os
	from pathlib import Path

	logger.info("GET /repos/test-results/%s received", filename)

	# Security: prevent path traversal
	if ".." in filename or "/" in filename or "\\" in filename:
		raise HTTPException(status_code=400, detail="Invalid filename")

	results_dir = Path(__file__).parent.parent / "data" / "test_results"
	file_path = results_dir / filename

	if not file_path.exists():
		raise HTTPException(status_code=404, detail=f"Test result file not found: {filename}")

	if not file_path.is_file():
		raise HTTPException(status_code=400, detail="Invalid file path")

	try:
		with open(file_path, "r", encoding="utf-8") as f:
			file_data = json.load(f)
		
		return {
			"status": "ok",
			"filename": filename,
			"data": file_data,
		}
	except json.JSONDecodeError as e:
		raise HTTPException(status_code=500, detail=f"Invalid JSON in test result file: {e}")
	except Exception as e:
		logger.error("Error reading test result file: %s", e, exc_info=True)
		raise HTTPException(status_code=500, detail=f"Error reading test result file: {e}")


class ForkRequest(BaseModel):
	repo_url: str
	org: str | None = None


@app.post("/repos/fork")
async def create_fork(payload: ForkRequest):
	logger.info("POST /repos/fork received: repo_url=%s, org=%s", payload.repo_url, payload.org)
	try:
		result = await fork_repository(str(payload.repo_url).strip(), payload.org)
		# Only log minimal success info; GitHub payload could be large
		logger.info("Fork requested successfully")
		return {"status": "ok", "data": result}
	except ValueError as ve:
		logger.warning("Validation error on fork request: %s", ve)
		raise HTTPException(status_code=400, detail=str(ve))
	except Exception as e:
		logger.error("Fork request failed: %s", e, exc_info=True)
		raise HTTPException(status_code=502, detail=str(e))


@app.post("/repos/test")
async def submit_test_case(
	background_tasks: BackgroundTasks,
	repo_url: str = Form(...),
	org: str | None = Form(None),
	tech_stack: str = Form(...),
	test_case_file: UploadFile = File(...),
):
	"""
	Submit test case JSON (DSL format) for a repository.
	Requires the repository to exist in the database (must be forked first).
	"""
	logger.info(
		"POST /repos/test received: repo_url=%s, org=%s, tech_stack=%s",
		repo_url,
		org,
		tech_stack,
	)

	# Validate tech_stack
	valid_tech_stacks = ["springboot_maven", "nodejs_express", "python_flask"]
	if tech_stack not in valid_tech_stacks:
		raise HTTPException(
			status_code=400,
			detail=f"Invalid tech_stack. Must be one of: {', '.join(valid_tech_stacks)}",
		)

	# Parse repository URL
	parsed = parse_repo_url(repo_url.strip())
	if not parsed:
		raise HTTPException(status_code=400, detail="Invalid GitHub repository URL")
	owner, repo = parsed
	repo_full_name = f"{owner}/{repo}"

	# Normalize org (strip if provided)
	normalized_org = org.strip() if org and org.strip() else None

	# Check if repository exists in database
	exists = await repository_exists(repo_full_name, normalized_org)
	if not exists:
		raise HTTPException(
			status_code=404,
			detail=f"Repository {repo_full_name} (org={normalized_org}) not found in database. Please fork it first.",
		)

	# Read and parse JSON file
	try:
		content = await test_case_file.read()
		test_case_json = json.loads(content.decode("utf-8"))
	except json.JSONDecodeError as e:
		logger.warning("Invalid JSON in test case file: %s", e)
		raise HTTPException(status_code=400, detail=f"Invalid JSON file: {e}")
	except Exception as e:
		logger.error("Error reading test case file: %s", e, exc_info=True)
		raise HTTPException(status_code=500, detail=f"Error reading file: {e}")

	# Save test case to file system
	try:
		file_path = await save_test_case(owner, repo, normalized_org, test_case_json)
		logger.info("Test case saved successfully: %s", file_path)
	except Exception as e:
		logger.error("Error saving test case: %s", e, exc_info=True)
		raise HTTPException(status_code=500, detail=f"Error saving test case: {e}")

	# Schedule background task to push test case and workflow to GitHub, and trigger workflow
	# This allows the API to return immediately without waiting for GitHub operations
	background_tasks.add_task(
		_push_test_case_and_workflow,
		repo_full_name=repo_full_name,
		normalized_org=normalized_org,
		tech_stack=tech_stack,
	)

	return {
		"status": "ok",
		"message": "Test case saved successfully. Pushing to GitHub and triggering tests in background...",
		"file_path": file_path,
		"repo_full_name": repo_full_name,
		"org": normalized_org,
		"tech_stack": tech_stack,
		"note": "GitHub push and workflow trigger are running in background. Check GitHub Actions for test results.",
	}


@app.put("/repos/test")
async def update_test_case(
	background_tasks: BackgroundTasks,
	repo_url: str = Form(...),
	org: str | None = Form(None),
	tech_stack: str = Form(...),
	test_case_file: UploadFile = File(...),
):
	"""
	Update test case JSON (DSL format) for a repository.
	Requires the repository to exist in the database and the test case file to exist.
	"""
	logger.info(
		"PUT /repos/test received: repo_url=%s, org=%s, tech_stack=%s",
		repo_url,
		org,
		tech_stack,
	)

	# Validate tech_stack
	valid_tech_stacks = ["springboot_maven", "nodejs_express", "python_flask"]
	if tech_stack not in valid_tech_stacks:
		raise HTTPException(
			status_code=400,
			detail=f"Invalid tech_stack. Must be one of: {', '.join(valid_tech_stacks)}",
		)

	# Parse repository URL
	parsed = parse_repo_url(repo_url.strip())
	if not parsed:
		raise HTTPException(status_code=400, detail="Invalid GitHub repository URL")
	owner, repo = parsed
	repo_full_name = f"{owner}/{repo}"

	# Normalize org (strip if provided)
	normalized_org = org.strip() if org and org.strip() else None

	# Check if repository exists in database
	exists = await repository_exists(repo_full_name, normalized_org)
	if not exists:
		raise HTTPException(
			status_code=404,
			detail=f"Repository {repo_full_name} (org={normalized_org}) not found in database. Please fork it first.",
		)

	# Check if test case file exists
	file_exists = await test_case_exists(owner, repo, normalized_org)
	if not file_exists:
		raise HTTPException(
			status_code=404,
			detail=f"Test case file for {repo_full_name} (org={normalized_org}) not found. Please submit it first using POST /repos/test.",
		)

	# Read and parse JSON file
	try:
		content = await test_case_file.read()
		test_case_json = json.loads(content.decode("utf-8"))
	except json.JSONDecodeError as e:
		logger.warning("Invalid JSON in test case file: %s", e)
		raise HTTPException(status_code=400, detail=f"Invalid JSON file: {e}")
	except Exception as e:
		logger.error("Error reading test case file: %s", e, exc_info=True)
		raise HTTPException(status_code=500, detail=f"Error reading file: {e}")

	# Update test case file
	try:
		file_path = await save_test_case(owner, repo, normalized_org, test_case_json)
		logger.info("Test case updated successfully: %s", file_path)
	except Exception as e:
		logger.error("Error updating test case: %s", e, exc_info=True)
		raise HTTPException(status_code=500, detail=f"Error updating test case: {e}")

	# Schedule background task to push test case and workflow to GitHub, and trigger workflow
	# This allows the API to return immediately without waiting for GitHub operations
	background_tasks.add_task(
		_push_test_case_and_workflow,
		repo_full_name=repo_full_name,
		normalized_org=normalized_org,
		tech_stack=tech_stack,
	)

	return {
		"status": "ok",
		"message": "Test case updated successfully. Pushing to GitHub and triggering tests in background...",
		"file_path": file_path,
		"repo_full_name": repo_full_name,
		"org": normalized_org,
		"tech_stack": tech_stack,
		"note": "GitHub push and workflow trigger are running in background. Check GitHub Actions for test results.",
	}



class DeleteRepositoryRequest(BaseModel):
	repo_url: str
	org: str | None = None


@app.delete("/repos")
async def delete_repository_endpoint(payload: DeleteRepositoryRequest):
	"""
	Delete a repository from local cache.
	Removes cache from database and deletes test case file if exists.
	Note: This does NOT delete the repository from GitHub.
	"""
	logger.info("DELETE /repos received: repo_url=%s, org=%s", payload.repo_url, payload.org)

	# Parse repository URL
	parsed = parse_repo_url(payload.repo_url.strip())
	if not parsed:
		raise HTTPException(status_code=400, detail="Invalid GitHub repository URL")
	original_owner, repo = parsed
	repo_full_name = f"{original_owner}/{repo}"

	# Normalize org
	normalized_org = payload.org.strip() if payload.org and payload.org.strip() else None

	# Check if repository exists in database
	exists = await repository_exists(repo_full_name, normalized_org)
	if not exists:
		raise HTTPException(
			status_code=404,
			detail=f"Repository {repo_full_name} (org={normalized_org}) not found in database.",
		)

	# Delete from database
	db_deleted = False
	try:
		db_deleted = await delete_cached_response(repo_full_name, normalized_org)
		logger.info("Repository deleted from database: %s", repo_full_name)
	except Exception as e:
		logger.error("Error deleting repository from database: %s", e, exc_info=True)
		raise HTTPException(status_code=500, detail=f"Error deleting repository from database: {e}")

	# Delete test case file if exists
	test_case_deleted = False
	try:
		test_case_deleted = await delete_test_case(original_owner, repo, normalized_org)
		if test_case_deleted:
			logger.info("Test case file deleted")
	except Exception as e:
		logger.error("Error deleting test case file: %s", e, exc_info=True)
		# Don't fail the request if test case deletion fails

	# Return result
	result = {
		"status": "ok",
		"message": "Repository deleted from local cache successfully",
		"repo_full_name": repo_full_name,
		"org": normalized_org,
		"deleted_from": {
			"database": db_deleted,
			"test_case_file": test_case_deleted,
		},
	}

	return result


async def _push_test_case_and_workflow(
	repo_full_name: str,
	normalized_org: str | None,
	tech_stack: str,
	backend_api_url: str | None = None,
) -> dict:
	"""
	Helper function to push test case and workflow to GitHub repository.
	Returns dict with push results.
	"""
	import os
	from pathlib import Path
	
	# Parse repository URL to get owner and repo
	parsed = parse_repo_url(f"https://github.com/{repo_full_name}")
	if not parsed:
		raise ValueError(f"Invalid repository full name: {repo_full_name}")
	original_owner, repo = parsed

	# Get fork information from cache
	fork_info = await get_cached_response(repo_full_name, normalized_org)
	if not fork_info:
		raise ValueError(f"Fork information for {repo_full_name} (org={normalized_org}) not found in cache.")

	# Extract fork owner and repo name from fork response
	fork_owner = fork_info.get("owner", {}).get("login")
	if not fork_owner:
		raise ValueError("Failed to extract fork owner from cached response.")
	fork_repo = fork_info.get("name", repo)
	fork_full_name = fork_info.get("full_name", f"{fork_owner}/{fork_repo}")
	
	# Get default branch
	default_branch = fork_info.get("default_branch", "main")
	if default_branch not in ["main", "master"]:
		default_branch = "main"

	# Check if test case file exists
	test_case = await load_test_case(original_owner, repo, normalized_org)
	if not test_case:
		raise ValueError(f"Test case file for {repo_full_name} not found.")

	# Get backend API URL
	api_url = backend_api_url or os.getenv("BACKEND_API_URL", "http://localhost:8000")

	results = {
		"files_pushed": [],
		"workflow_triggered": False,
		"fork_full_name": fork_full_name,
	}

	# Check if this is the first time pushing test files (check if test_case.json exists in repo)
	test_case_exists_in_repo = await get_file_content(
		fork_owner=fork_owner,
		repo=fork_repo,
		path="test_case.json",
		branch=default_branch,
	)
	is_first_push = test_case_exists_in_repo is None

	# Push test runner files on first push
	if is_first_push:
		logger.info("First push detected, pushing test runner files...")
		
		# Files to push: test-runner.js, schema/jsonSchemaValidator.js, schema/schema.json
		test_files = [
			("test-runner.js", "test-runner.js"),
			("schema/jsonSchemaValidator.js", "schema/jsonSchemaValidator.js"),
			("schema/schema.json", "schema/schema.json"),
		]
		
		for local_path, repo_path in test_files:
			try:
				file_path = Path(__file__).parent.parent / local_path
				if not file_path.exists():
					logger.warning("Test file not found locally: %s, skipping...", local_path)
					continue
				
				# Check if file already exists in repo
				existing_file = await get_file_content(
					fork_owner=fork_owner,
					repo=fork_repo,
					path=repo_path,
					branch=default_branch,
				)
				
				if existing_file is None:
					# Read file content
					with open(file_path, "r", encoding="utf-8") as f:
						file_content = f.read()
					
					# Push file
					await create_or_update_file(
						fork_owner=fork_owner,
						repo=fork_repo,
						path=repo_path,
						content=file_content,
						message=f"Add {repo_path} for API testing [skip ci]",
						branch=default_branch,
					)
					results["files_pushed"].append(repo_path)
					logger.info("Test file pushed successfully: %s", repo_path)
				else:
					logger.info("Test file already exists in repo: %s, skipping...", repo_path)
			except Exception as e:
				logger.warning("Error pushing test file %s: %s, continuing...", local_path, e, exc_info=True)
				# Don't fail the whole process if test file push fails

	# Push test case file
	try:
		test_case_json_str = json.dumps(test_case, indent=2, ensure_ascii=False)
		await create_or_update_file(
			fork_owner=fork_owner,
			repo=fork_repo,
			path="test_case.json",
			content=test_case_json_str,
			message="Update test case file [skip ci]",
			branch=default_branch,
		)
		results["files_pushed"].append("test_case.json")
		logger.info("Test case file pushed successfully to %s", fork_full_name)
	except Exception as e:
		logger.error("Error pushing test case file: %s", e, exc_info=True)
		raise

	# Generate and push GitHub Actions workflow
	workflow_was_new = False
	try:
		workflow_content = generate_workflow(
			tech_stack=tech_stack,
			test_case_path="test_case.json",
			backend_api_url=api_url,
		)
		# Check if workflow file exists and if content has changed
		existing_workflow = await get_file_content(
			fork_owner=fork_owner,
			repo=fork_repo,
			path=".github/workflows/api-test.yml",
			branch=default_branch,
		)
		workflow_was_new = existing_workflow is None
		
		# Decode existing workflow content to compare
		workflow_needs_update = True
		if existing_workflow and "content" in existing_workflow:
			import base64
			try:
				existing_content = base64.b64decode(existing_workflow["content"]).decode("utf-8")
				# Normalize both contents (remove trailing whitespace/newlines)
				if existing_content.strip() == workflow_content.strip():
					workflow_needs_update = False
					logger.info("Workflow content unchanged, skipping update")
			except Exception as e:
				logger.warning("Failed to decode existing workflow content for comparison: %s", e)
		
		if workflow_needs_update:
			await create_or_update_file(
				fork_owner=fork_owner,
				repo=fork_repo,
				path=".github/workflows/api-test.yml",
				content=workflow_content,
				message="Update GitHub Actions workflow for API testing [skip ci]",
				branch=default_branch,
			)
			results["files_pushed"].append(".github/workflows/api-test.yml")
			logger.info("GitHub Actions workflow pushed successfully to %s", fork_full_name)
			
			# If workflow was newly created, wait a bit for GitHub to register it
			if workflow_was_new:
				import asyncio
				logger.info("Workflow file is new, waiting 3 seconds for GitHub to register it...")
				await asyncio.sleep(3)
		else:
			logger.info("Workflow file unchanged, not pushing")
	except Exception as e:
		logger.error("Error pushing GitHub Actions workflow: %s", e, exc_info=True)
		raise

	# Trigger the workflow (only once, after all files are pushed)
	try:
		trigger_result = await trigger_workflow(
			fork_owner=fork_owner,
			repo=fork_repo,
			workflow_id="api-test.yml",
			branch=default_branch,
		)
		results["workflow_triggered"] = True
		results["workflow_trigger_id"] = trigger_result.get("workflow_id")
		logger.info("GitHub Actions workflow triggered successfully")
	except Exception as e:
		# Don't fail if workflow trigger fails (workflow might not exist yet on first push)
		logger.warning("Failed to trigger workflow: %s", e)
		results["workflow_trigger_error"] = str(e)

	return results


class PushTestCaseRequest(BaseModel):
	repo_url: str
	org: str | None = None
	tech_stack: str
	backend_api_url: str | None = None


class UpdateWorkflowRequest(BaseModel):
	repo_url: str
	org: str | None = None
	tech_stack: str | None = None
	backend_api_url: str | None = None


@app.post("/repos/push-test")
async def push_test_case_to_repo(payload: PushTestCaseRequest):
	"""
	Push test case file and GitHub Actions workflow to the forked repository.
	Requires the repository to be forked and test case file to exist.
	"""
	logger.info(
		"POST /repos/push-test received: repo_url=%s, org=%s, tech_stack=%s",
		payload.repo_url,
		payload.org,
		payload.tech_stack,
	)

	# Validate tech_stack
	valid_tech_stacks = ["springboot_maven", "nodejs_express", "python_flask"]
	if payload.tech_stack not in valid_tech_stacks:
		raise HTTPException(
			status_code=400,
			detail=f"Invalid tech_stack. Must be one of: {', '.join(valid_tech_stacks)}",
		)

	# Parse repository URL
	parsed = parse_repo_url(payload.repo_url.strip())
	if not parsed:
		raise HTTPException(status_code=400, detail="Invalid GitHub repository URL")
	original_owner, repo = parsed
	repo_full_name = f"{original_owner}/{repo}"

	# Normalize org
	normalized_org = payload.org.strip() if payload.org and payload.org.strip() else None

	# Check if repository exists in database
	exists = await repository_exists(repo_full_name, normalized_org)
	if not exists:
		raise HTTPException(
			status_code=404,
			detail=f"Repository {repo_full_name} (org={normalized_org}) not found in database. Please fork it first.",
		)

	# Get fork information from cache
	fork_info = await get_cached_response(repo_full_name, normalized_org)
	if not fork_info:
		raise HTTPException(
			status_code=404,
			detail=f"Fork information for {repo_full_name} (org={normalized_org}) not found in cache.",
		)

	# Extract fork owner and repo name from fork response
	fork_owner = fork_info.get("owner", {}).get("login")
	if not fork_owner:
		raise HTTPException(
			status_code=500,
			detail="Failed to extract fork owner from cached response. Please fork the repository again.",
		)
	fork_repo = fork_info.get("name", repo)
	fork_full_name = fork_info.get("full_name", f"{fork_owner}/{fork_repo}")
	
	# Get default branch (default to "main", fallback to "master")
	default_branch = fork_info.get("default_branch", "main")
	if default_branch not in ["main", "master"]:
		default_branch = "main"  # Fallback to main if unknown

	# Check if test case file exists
	test_case = await load_test_case(original_owner, repo, normalized_org)
	if not test_case:
		raise HTTPException(
			status_code=404,
			detail=f"Test case file for {repo_full_name} (org={normalized_org}) not found. Please submit it first using POST /repos/test.",
		)

	# Get backend API URL (from payload or environment variable)
	import os
	backend_api_url = payload.backend_api_url or os.getenv("BACKEND_API_URL", "http://localhost:8000")

	# Prepare results
	results = {
		"status": "ok",
		"message": "Test case and workflow pushed successfully",
		"repo_full_name": repo_full_name,
		"fork_full_name": fork_full_name,
		"org": normalized_org,
		"tech_stack": payload.tech_stack,
		"files_pushed": [],
	}

	# Push test case file
	try:
		test_case_json_str = json.dumps(test_case, indent=2, ensure_ascii=False)
		test_case_result = await create_or_update_file(
			fork_owner=fork_owner,
			repo=fork_repo,
			path="test_case.json",
			content=test_case_json_str,
			message="Add test case file",
			branch=default_branch,
		)
		results["files_pushed"].append("test_case.json")
		logger.info("Test case file pushed successfully to %s", fork_full_name)
	except Exception as e:
		logger.error("Error pushing test case file: %s", e, exc_info=True)
		raise HTTPException(status_code=500, detail=f"Error pushing test case file: {e}")

	# Generate and push GitHub Actions workflow
	try:
		workflow_content = generate_workflow(
			tech_stack=payload.tech_stack,
			test_case_path="test_case.json",
			backend_api_url=backend_api_url,
		)
		workflow_result = await create_or_update_file(
			fork_owner=fork_owner,
			repo=fork_repo,
			path=".github/workflows/api-test.yml",
			content=workflow_content,
			message="Add GitHub Actions workflow for API testing [skip ci]",
			branch=default_branch,
		)
		results["files_pushed"].append(".github/workflows/api-test.yml")
		logger.info("GitHub Actions workflow pushed successfully to %s", fork_full_name)
	except Exception as e:
		logger.error("Error pushing GitHub Actions workflow: %s", e, exc_info=True)
		raise HTTPException(status_code=500, detail=f"Error pushing GitHub Actions workflow: {e}")

	return results


@app.put("/repos/update-workflow")
async def update_workflow(payload: UpdateWorkflowRequest):
	"""
	Update the GitHub Actions workflow file in the forked repository.
	This will regenerate the workflow using the latest workflow_generator.py logic.
	Requires the repository to be forked.
	
	If tech_stack is not provided, it will try to infer from existing workflow or test case.
	"""
	logger.info(
		"PUT /repos/update-workflow received: repo_url=%s, org=%s, tech_stack=%s",
		payload.repo_url,
		payload.org,
		payload.tech_stack,
	)

	# Parse repository URL
	parsed = parse_repo_url(payload.repo_url.strip())
	if not parsed:
		raise HTTPException(status_code=400, detail="Invalid GitHub repository URL")
	original_owner, repo = parsed
	repo_full_name = f"{original_owner}/{repo}"

	# Normalize org
	normalized_org = payload.org.strip() if payload.org and payload.org.strip() else None

	# Check if repository exists in database
	exists = await repository_exists(repo_full_name, normalized_org)
	if not exists:
		raise HTTPException(
			status_code=404,
			detail=f"Repository {repo_full_name} (org={normalized_org}) not found in database. Please fork it first.",
		)

	# Get fork information from cache
	fork_info = await get_cached_response(repo_full_name, normalized_org)
	if not fork_info:
		raise HTTPException(
			status_code=404,
			detail=f"Fork information for {repo_full_name} (org={normalized_org}) not found in cache.",
		)

	# Extract fork owner and repo name from fork response
	fork_owner = fork_info.get("owner", {}).get("login")
	if not fork_owner:
		raise HTTPException(
			status_code=500,
			detail="Failed to extract fork owner from cached response. Please fork the repository again.",
		)
	fork_repo = fork_info.get("name", repo)
	fork_full_name = fork_info.get("full_name", f"{fork_owner}/{fork_repo}")
	
	# Get default branch (default to "main", fallback to "master")
	default_branch = fork_info.get("default_branch", "main")
	if default_branch not in ["main", "master"]:
		default_branch = "main"  # Fallback to main if unknown

	# Determine tech_stack if not provided
	tech_stack = payload.tech_stack
	if not tech_stack:
		# Try to get tech_stack from existing test case metadata or workflow
		# For now, we'll require it to be provided, but we could enhance this later
		raise HTTPException(
			status_code=400,
			detail="tech_stack is required. Please provide one of: springboot_maven, nodejs_express, python_flask",
		)

	# Validate tech_stack
	valid_tech_stacks = ["springboot_maven", "nodejs_express", "python_flask"]
	if tech_stack not in valid_tech_stacks:
		raise HTTPException(
			status_code=400,
			detail=f"Invalid tech_stack. Must be one of: {', '.join(valid_tech_stacks)}",
		)

	# Get backend API URL (from payload or environment variable)
	import os
	backend_api_url = payload.backend_api_url or os.getenv("BACKEND_API_URL", "http://localhost:8000")

	# Prepare results
	results = {
		"status": "ok",
		"message": "Workflow updated successfully",
		"repo_full_name": repo_full_name,
		"fork_full_name": fork_full_name,
		"org": normalized_org,
		"tech_stack": tech_stack,
		"workflow_updated": False,
	}

	# Generate and push GitHub Actions workflow
	try:
		workflow_content = generate_workflow(
			tech_stack=tech_stack,
			test_case_path="test_case.json",
			backend_api_url=backend_api_url,
		)
		
		# Check if workflow file exists
		existing_workflow = await get_file_content(
			fork_owner=fork_owner,
			repo=fork_repo,
			path=".github/workflows/api-test.yml",
			branch=default_branch,
		)
		
		if existing_workflow is None:
			logger.warning("Workflow file does not exist in repository, creating new one")
		
		# Always update the workflow (since user explicitly requested it)
		await create_or_update_file(
			fork_owner=fork_owner,
			repo=fork_repo,
			path=".github/workflows/api-test.yml",
			content=workflow_content,
			message="Update GitHub Actions workflow for API testing [skip ci]",
			branch=default_branch,
		)
		results["workflow_updated"] = True
		logger.info("GitHub Actions workflow updated successfully in %s", fork_full_name)
		
		# If workflow was newly created, wait a bit for GitHub to register it
		if existing_workflow is None:
			import asyncio
			logger.info("Workflow file is new, waiting 3 seconds for GitHub to register it...")
			await asyncio.sleep(3)
			
	except Exception as e:
		logger.error("Error updating GitHub Actions workflow: %s", e, exc_info=True)
		raise HTTPException(status_code=500, detail=f"Error updating GitHub Actions workflow: {e}")

	return results


class SyncForkRequest(BaseModel):
	repo_url: str
	org: str | None = None
	branch: str | None = "main"


@app.post("/repos/sync-upstream")
async def sync_fork(payload: SyncForkRequest):
	"""
	Trigger a sync of a forked repository with its upstream using the server account.
	Request JSON: {"repo_url": "https://github.com/owner/repo", "org": "optional-org", "branch": "main"}
	"""
	logger.info("POST /repos/sync-upstream received: repo_url=%s, org=%s, branch=%s", payload.repo_url, payload.org, payload.branch)

	# Parse repository URL
	parsed = parse_repo_url(payload.repo_url.strip())
	if not parsed:
		raise HTTPException(status_code=400, detail="Invalid GitHub repository URL")
	original_owner, repo = parsed
	repo_full_name = f"{original_owner}/{repo}"

	# Normalize org
	normalized_org = payload.org.strip() if payload.org and payload.org.strip() else None

	# Check repository exists in local cache
	exists = await repository_exists(repo_full_name, normalized_org)
	if not exists:
		raise HTTPException(status_code=404, detail=f"Repository {repo_full_name} (org={normalized_org}) not found in database. Please fork it first.")

	# Get fork info from cache
	fork_info = await get_cached_response(repo_full_name, normalized_org)
	if not fork_info:
		raise HTTPException(status_code=404, detail=f"Fork information for {repo_full_name} (org={normalized_org}) not found in cache.")

	fork_owner = fork_info.get("owner", {}).get("login")
	if not fork_owner:
		raise HTTPException(status_code=500, detail="Failed to extract fork owner from cached response. Please fork the repository again.")
	fork_repo = fork_info.get("name", repo)

	# Branch default
	branch = payload.branch or "main"

	# Call GitHub API to merge upstream into fork
	try:
		result = await merge_upstream(fork_owner=fork_owner, repo=fork_repo, branch=branch)
		# result may be dict or empty; return a friendly response
		return {
			"status": "ok",
			"message": "Sync request sent to GitHub",
			"repo_full_name": repo_full_name,
			"fork_full_name": fork_info.get("full_name"),
			"branch": branch,
			"data": result,
		}
	except Exception as e:
		logger.error("Error syncing fork: %s", e, exc_info=True)
		# If it's an HTTPStatusError from httpx, surface as 502
		from httpx import HTTPStatusError
		if isinstance(e, HTTPStatusError):
			raise HTTPException(status_code=502, detail=str(e))
		raise HTTPException(status_code=500, detail=str(e))