import argparse
import os
from typing import Optional

import httpx
from dotenv import load_dotenv


def fetch_user_and_scopes(token: str, timeout_seconds: float = 15.0) -> tuple[dict, dict]:
	headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
	with httpx.Client(timeout=timeout_seconds) as client:
		resp = client.get("https://api.github.com/user", headers=headers)
		return resp.json(), dict(resp.headers)


def main(argv: Optional[list[str]] = None) -> int:
	parser = argparse.ArgumentParser(description="Test a GitHub Personal Access Token (PAT).")
	parser.add_argument("--token", type=str, help="GitHub PAT. If omitted, reads from env GITHUB_PAT")
	parser.add_argument("--show-headers", action="store_true", help="Print all response headers")
	args = parser.parse_args(argv)

	load_dotenv()
	token = args.token or os.getenv("GITHUB_PAT") or ""
	if not token:
		print("ERROR: No token provided. Use --token or set GITHUB_PAT in environment/.env")
		return 2

	try:
		body, headers = fetch_user_and_scopes(token)
	except Exception as e:
		print(f"ERROR: Request failed: {e}")
		return 3

	status = body.get("message") if "message" in body and "login" not in body else "OK"
	login = body.get("login")
	user_id = body.get("id")

	scopes = headers.get("X-OAuth-Scopes", "")
	rate_limit = headers.get("X-RateLimit-Limit", "")
	rate_remaining = headers.get("X-RateLimit-Remaining", "")

	print("=== PAT Check Result ===")
	print(f"Status         : {status}")
	print(f"Login          : {login}")
	print(f"User ID        : {user_id}")
	print(f"Scopes         : {scopes}")
	print(f"Rate Limit     : {rate_limit} (remaining {rate_remaining})")

	if args.show_headers:
		print("\n=== Response Headers ===")
		for k, v in headers.items():
			print(f"{k}: {v}")

	# Basic guidance
	if "repo" not in scopes and "public_repo" not in scopes:
		print("\nHint: Missing 'public_repo' (public) or 'repo' (private) scope for forking.")

	return 0


if __name__ == "__main__":
	raise SystemExit(main())


