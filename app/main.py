import logging

from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel

from .github_client import fork_repository
from .logging_config import configure_logging

configure_logging()
app = FastAPI(title="DPostBackend", version="0.1.0")
logger = logging.getLogger("app.main")


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


