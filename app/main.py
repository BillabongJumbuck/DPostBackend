from fastapi import FastAPI

app = FastAPI(title="DPostBackend", version="0.1.0")


@app.get("/health")
def health_check():
	app_state = {"status": "ok"}
	return app_state


@app.get("/")
def read_root():
	return {"message": "Welcome to DPostBackend (FastAPI)"}


