import logging
import os
from typing import Optional

from dotenv import load_dotenv


def _parse_level(level_str: Optional[str]) -> int:
	if not level_str:
		return logging.INFO
	level_str = level_str.strip().upper()
	return {
		"DEBUG": logging.DEBUG,
		"INFO": logging.INFO,
		"WARNING": logging.WARNING,
		"ERROR": logging.ERROR,
		"CRITICAL": logging.CRITICAL,
	}.get(level_str, logging.INFO)


def configure_logging() -> None:
	# load env first so LOG_LEVEL is available
	load_dotenv()

	log_level = _parse_level(os.getenv("LOG_LEVEL"))
	log_format = "%(asctime)s %(levelname)s %(name)s - %(message)s"
	datefmt = "%Y-%m-%d %H:%M:%S"

	# Configure root logger only once
	if not logging.getLogger().handlers:
		logging.basicConfig(level=log_level, format=log_format, datefmt=datefmt)
	else:
		logging.getLogger().setLevel(log_level)

	# Be quieter for verbose libraries by default
	logging.getLogger("httpx").setLevel(max(logging.WARNING, log_level))
	logging.getLogger("uvicorn.access").setLevel(max(logging.INFO, log_level))


