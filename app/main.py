from fastapi import FastAPI
from fastapi import HTTPException
from pydantic import BaseModel, HttpUrl

from .github_client import fork_repository

app = FastAPI(title="DPostBackend", version="0.1.0")


@app.get("/health")
def health_check():
	app_state = {"status": "ok"}
	return app_state


@app.get("/")
def read_root():
	return {"message": "Welcome to DPostBackend (FastAPI)"}


class ForkRequest(BaseModel):
	repo_url: HttpUrl
	org: str | None = None


@app.post("/repos/fork")
async def create_fork(payload: ForkRequest):
	try:
		result = await fork_repository(str(payload.repo_url), payload.org)
		return {"status": "ok", "data": result}
	except ValueError as ve:
		raise HTTPException(status_code=400, detail=str(ve))
	except Exception as e:
		raise HTTPException(status_code=502, detail=str(e))


