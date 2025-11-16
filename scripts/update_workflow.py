#!/usr/bin/env python3
"""
Script to update GitHub Actions workflow file in a forked repository.
Calls the PUT /repos/update-workflow API endpoint.
"""

import argparse
import json
import os
import sys
from typing import Optional

import httpx

try:
	from dotenv import load_dotenv
except ImportError:
	# dotenv is optional
	def load_dotenv():
		pass


def update_workflow(
	api_base_url: str,
	repo_url: str,
	org: Optional[str] = None,
	tech_stack: Optional[str] = None,
	backend_api_url: Optional[str] = None,
	timeout_seconds: float = 30.0,
) -> tuple[dict, int]:
	"""
	Call the PUT /repos/update-workflow API endpoint.
	
	Returns:
		Tuple of (response_json, status_code)
	"""
	url = f"{api_base_url.rstrip('/')}/repos/update-workflow"
	
	payload = {
		"repo_url": repo_url,
	}
	
	if org:
		payload["org"] = org
	if tech_stack:
		payload["tech_stack"] = tech_stack
	if backend_api_url:
		payload["backend_api_url"] = backend_api_url
	
	with httpx.Client(timeout=timeout_seconds) as client:
		resp = client.put(url, json=payload)
		try:
			return resp.json(), resp.status_code
		except Exception:
			return {"error": resp.text}, resp.status_code


def main(argv: Optional[list[str]] = None) -> int:
	parser = argparse.ArgumentParser(
		description="Update GitHub Actions workflow file in a forked repository.",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog="""
Examples:
  # Update workflow for a repository
  python scripts/update_workflow.py --repo-url https://github.com/owner/repo --tech-stack springboot_maven
  
  # Update workflow with org
  python scripts/update_workflow.py --repo-url https://github.com/owner/repo --org myorg --tech-stack nodejs_express
  
  # Update workflow with custom API URL
  python scripts/update_workflow.py --repo-url https://github.com/owner/repo --tech-stack python_flask --api-url http://localhost:8000
		""",
	)
	
	parser.add_argument(
		"--repo-url",
		type=str,
		required=True,
		help="GitHub repository URL (e.g., https://github.com/owner/repo)",
	)
	parser.add_argument(
		"--org",
		type=str,
		default=None,
		help="Organization name (optional)",
	)
	parser.add_argument(
		"--tech-stack",
		type=str,
		required=True,
		choices=["springboot_maven", "nodejs_express", "python_flask"],
		help="Technology stack type",
	)
	parser.add_argument(
		"--backend-api-url",
		type=str,
		default=None,
		help="Backend API URL (optional, defaults to environment variable or http://localhost:8000)",
	)
	parser.add_argument(
		"--api-url",
		type=str,
		default=None,
		help="API base URL (defaults to http://localhost:8000 or API_BASE_URL env var)",
	)
	parser.add_argument(
		"--timeout",
		type=float,
		default=30.0,
		help="Request timeout in seconds (default: 30.0)",
	)
	parser.add_argument(
		"--json",
		action="store_true",
		help="Output result as JSON",
	)
	
	args = parser.parse_args(argv)
	
	load_dotenv()
	
	# Get API base URL
	api_base_url = args.api_url or os.getenv("API_BASE_URL", "http://localhost:8000")
	
	try:
		response_json, status_code = update_workflow(
			api_base_url=api_base_url,
			repo_url=args.repo_url,
			org=args.org,
			tech_stack=args.tech_stack,
			backend_api_url=args.backend_api_url,
			timeout_seconds=args.timeout,
		)
	except httpx.TimeoutException:
		print("ERROR: Request timeout", file=sys.stderr)
		return 3
	except Exception as e:
		print(f"ERROR: Request failed: {e}", file=sys.stderr)
		return 3
	
	if args.json:
		print(json.dumps(response_json, indent=2, ensure_ascii=False))
		return 0 if status_code == 200 else 1
	
	# Pretty print result
	if status_code == 200:
		print("=== Workflow Update Result ===")
		print(f"Status          : {response_json.get('status', 'unknown')}")
		print(f"Message         : {response_json.get('message', 'N/A')}")
		print(f"Repository      : {response_json.get('repo_full_name', 'N/A')}")
		print(f"Fork            : {response_json.get('fork_full_name', 'N/A')}")
		print(f"Organization    : {response_json.get('org', 'N/A')}")
		print(f"Tech Stack      : {response_json.get('tech_stack', 'N/A')}")
		print(f"Workflow Updated: {response_json.get('workflow_updated', False)}")
		return 0
	else:
		print("=== Error ===", file=sys.stderr)
		print(f"Status Code: {status_code}", file=sys.stderr)
		if "detail" in response_json:
			print(f"Error: {response_json['detail']}", file=sys.stderr)
		else:
			print(f"Response: {json.dumps(response_json, indent=2)}", file=sys.stderr)
		return 1


if __name__ == "__main__":
	raise SystemExit(main())

