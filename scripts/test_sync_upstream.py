#!/usr/bin/env python3
"""
Simple test script for POST /repos/sync-upstream
Usage:
  python scripts/test_sync_upstream.py --repo-url https://github.com/owner/repo [--org ORG] [--branch BRANCH] [--base-url http://127.0.0.1:8000]

This script reads optional `.env` for `BACKEND_API_URL` and uses it as default base URL.
It uses the `requests` library. If not installed, run `pip install requests python-dotenv`.
"""
import argparse
import json
import os
import sys
from pathlib import Path

try:
    import requests
except Exception:
    print("The 'requests' package is required. Install with: pip install requests")
    sys.exit(2)

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


def load_env(env_path: Path | str = ".env"):
    if load_dotenv:
        load_dotenv(dotenv_path=env_path)


def main():
    parser = argparse.ArgumentParser(description="Test POST /repos/sync-upstream endpoint")
    parser.add_argument("--repo-url", required=True, help="Original repository URL, e.g. https://github.com/owner/repo")
    parser.add_argument("--org", default=None, help="Optional organization name")
    parser.add_argument("--branch", default="main", help="Branch to sync (default: main)")
    parser.add_argument("--base-url", default=None, help="Backend base URL (overrides BACKEND_API_URL in .env)")
    parser.add_argument("--timeout", type=float, default=15.0, help="Request timeout in seconds")
    args = parser.parse_args()

    # Load .env if present
    load_env()

    base_url = args.base_url or os.getenv("BACKEND_API_URL") or "http://127.0.0.1:8000"
    endpoint = f"{base_url.rstrip('/')}/repos/sync-upstream"

    payload = {"repo_url": args.repo_url, "branch": args.branch}
    if args.org:
        payload["org"] = args.org

    headers = {"Content-Type": "application/json"}

    print(f"POST {endpoint}")
    print("Payload:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    try:
        r = requests.post(endpoint, json=payload, headers=headers, timeout=args.timeout)
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        sys.exit(3)

    print(f"Status: {r.status_code}")
    content_type = r.headers.get("Content-Type", "")
    if "application/json" in content_type:
        try:
            data = r.json()
            print(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception:
            print(r.text)
    else:
        print(r.text)

    # Exit codes by status class
    if 200 <= r.status_code < 300:
        sys.exit(0)
    elif 300 <= r.status_code < 400:
        sys.exit(0)
    elif 400 <= r.status_code < 500:
        sys.exit(4)
    else:
        sys.exit(5)


if __name__ == "__main__":
    main()
