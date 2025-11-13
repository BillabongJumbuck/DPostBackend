import json
import logging

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from .cache import delete_cached_response, repository_exists
from .database import init_db
from .github_client import fork_repository, parse_repo_url
from .logging_config import configure_logging
from .test_case_storage import delete_test_case, save_test_case, test_case_exists

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
	repo_url: str = Form(...),
	org: str | None = Form(None),
	tech_stack: str = Form(...),
	test_case_file: UploadFile = File(...),
):
	"""
	Submit OpenAPI test case for a repository.
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
		return {
			"status": "ok",
			"message": "Test case saved successfully",
			"file_path": file_path,
			"repo_full_name": repo_full_name,
			"org": normalized_org,
			"tech_stack": tech_stack,
		}
	except Exception as e:
		logger.error("Error saving test case: %s", e, exc_info=True)
		raise HTTPException(status_code=500, detail=f"Error saving test case: {e}")


@app.put("/repos/test")
async def update_test_case(
	repo_url: str = Form(...),
	org: str | None = Form(None),
	tech_stack: str = Form(...),
	test_case_file: UploadFile = File(...),
):
	"""
	Update OpenAPI test case for a repository.
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
		return {
			"status": "ok",
			"message": "Test case updated successfully",
			"file_path": file_path,
			"repo_full_name": repo_full_name,
			"org": normalized_org,
			"tech_stack": tech_stack,
		}
	except Exception as e:
		logger.error("Error updating test case: %s", e, exc_info=True)
		raise HTTPException(status_code=500, detail=f"Error updating test case: {e}")



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