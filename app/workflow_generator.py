"""
Generate GitHub Actions workflow files for different tech stacks.
"""
import logging
import os
from typing import Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger("app.workflow_generator")

# Backend API URL - loaded from environment variable or default
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000")


def generate_workflow(
	tech_stack: str,
	test_case_path: str = "test_case.json",
	backend_api_url: str | None = None,
) -> str:
	"""
	Generate GitHub Actions workflow YAML content based on tech stack.
	
	Args:
		tech_stack: One of "springboot_maven", "nodejs_express", "python_flask"
		test_case_path: Path to test case JSON file in repository
		backend_api_url: Backend API URL to send test results to
	
	Returns:
		YAML content for GitHub Actions workflow
	"""
	api_url = backend_api_url or BACKEND_API_URL

	if tech_stack == "springboot_maven":
		return _generate_springboot_workflow(test_case_path, api_url)
	elif tech_stack == "nodejs_express":
		return _generate_nodejs_workflow(test_case_path, api_url)
	elif tech_stack == "python_flask":
		return _generate_python_flask_workflow(test_case_path, api_url)
	else:
		raise ValueError(f"Unsupported tech_stack: {tech_stack}")


def _generate_springboot_workflow(test_case_path: str, backend_api_url: str) -> str:
	"""Generate workflow for Spring Boot Maven projects."""
	return f"""name: API Test

on:
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          java-version: '17'
          distribution: 'temurin'
          cache: maven
      
      - name: Build application
        run: mvn clean package -DskipTests
      
      - name: Start application
        run: |
          echo "Starting Spring Boot application..."
          java -jar target/*.jar > app.log 2>&1 &
          APP_PID=$!
          echo "Application started with PID: $APP_PID"
          echo "Waiting 30 seconds for initial startup..."
          sleep 30
          echo "Checking if application process is still running..."
          if ! ps -p $APP_PID > /dev/null; then
            echo "ERROR: Application process died during startup!"
            echo "=== Application Logs ==="
            cat app.log || true
            exit 1
          fi
          echo "Application process is running (PID: $APP_PID)"
        env:
          SPRING_PROFILES_ACTIVE: test
      
      - name: Wait for application to be ready
        run: |
            echo "Waiting for port 8080..."
            for i in {{1..60}}; do
            if nc -z localhost 8080; then
                echo "Application is ready!"
                exit 0
            fi
            sleep 2
            done
            echo "ERROR: Application did not open port 8080"
            exit 1
      
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      
      - name: Run API tests
        id: test
        run: |
          node test-runner.js {test_case_path}
      
      - name: Send test results to backend
        if: always()
        run: |
          if [ -f test_results.json ]; then
            echo "Sending test results to backend..."
            REPO_URL="${{{{ github.repository }}}}"
            ORG="${{{{ github.repository_owner }}}}"
            WORKFLOW_RUN_ID="${{{{ github.run_id }}}}"
            WORKFLOW_RUN_URL="${{{{ github.server_url }}}}/${{{{ github.repository }}}}/actions/runs/${{{{ github.run_id }}}}"
            
            # Build JSON payload using jq
            PAYLOAD=$(jq -n \\
              --arg repo_url "https://github.com/$REPO_URL" \\
              --arg org "$ORG" \\
              --arg workflow_run_id "$WORKFLOW_RUN_ID" \\
              --arg workflow_run_url "$WORKFLOW_RUN_URL" \\
              --slurpfile test_results test_results.json \\
              '{{repo_url: $repo_url, org: $org, workflow_run_id: $workflow_run_id, workflow_run_url: $workflow_run_url, test_results: $test_results[0]}}')
            
            curl -X POST "${{{{ env.backend_api_url }}}}/repos/test-results" \\
              -H "Content-Type: application/json" \\
              -d "$PAYLOAD" || echo "Failed to send test results, but continuing..."
          else
            echo "test_results.json not found, skipping..."
          fi
        env:
          backend_api_url: {backend_api_url}
      
      - name: Stop application
        if: always()
        run: pkill -f "java -jar"
"""


def _generate_nodejs_workflow(test_case_path: str, backend_api_url: str) -> str:
	"""Generate workflow for Node.js Express projects."""
	return f"""name: API Test

on:
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
      
      - name: Install dependencies
        run: npm install
      
      - name: Start application
        run: |
          echo "Starting Node.js application..."
          npm start > app.log 2>&1 &
          APP_PID=$!
          echo "Application started with PID: $APP_PID"
          echo "Waiting 10 seconds for initial startup..."
          sleep 10
          echo "Checking if application process is still running..."
          if ! ps -p $APP_PID > /dev/null; then
            echo "ERROR: Application process died during startup!"
            echo "=== Application Logs ==="
            cat app.log || true
            exit 1
          fi
          echo "Application process is running (PID: $APP_PID)"
        env:
          NODE_ENV: test
          PORT: 3000
      
      - name: Wait for application to be ready
        run: |
          echo "Waiting for application to be ready..."
          timeout=120
          elapsed=0
          while ! curl -f http://localhost:3000/health 2>/dev/null; do
            if [ $elapsed -ge $timeout ]; then
              echo "ERROR: Application failed to start within $timeout seconds"
              echo "=== Checking application status ==="
              ps aux | grep node || true
              echo "=== Checking if port 3000 is listening ==="
              netstat -tlnp | grep 3000 || ss -tlnp | grep 3000 || true
              echo "=== Application Logs (last 50 lines) ==="
              tail -50 app.log || true
              echo "=== Trying to access root endpoint ==="
              curl -v http://localhost:3000/ || true
              exit 1
            fi
            echo "Waiting for application... (elapsed: ${{elapsed}}s)"
            sleep 2
            elapsed=$((elapsed + 2))
          done
          echo "Application is ready! Health check passed."
          echo "=== Application Logs (last 20 lines) ==="
          tail -20 app.log || true
      
      - name: Run API tests
        id: test
        run: |
          node test-runner.js {test_case_path}
      
      - name: Send test results to backend
        if: always()
        run: |
          if [ -f test_results.json ]; then
            echo "Sending test results to backend..."
            REPO_URL="${{{{ github.repository }}}}"
            ORG="${{{{ github.repository_owner }}}}"
            WORKFLOW_RUN_ID="${{{{ github.run_id }}}}"
            WORKFLOW_RUN_URL="${{{{ github.server_url }}}}/${{{{ github.repository }}}}/actions/runs/${{{{ github.run_id }}}}"
            
            # Build JSON payload using jq
            PAYLOAD=$(jq -n \\
              --arg repo_url "https://github.com/$REPO_URL" \\
              --arg org "$ORG" \\
              --arg workflow_run_id "$WORKFLOW_RUN_ID" \\
              --arg workflow_run_url "$WORKFLOW_RUN_URL" \\
              --slurpfile test_results test_results.json \\
              '{{repo_url: $repo_url, org: $org, workflow_run_id: $workflow_run_id, workflow_run_url: $workflow_run_url, test_results: $test_results[0]}}')
            
            curl -X POST "${{{{ env.backend_api_url }}}}/repos/test-results" \\
              -H "Content-Type: application/json" \\
              -d "$PAYLOAD" || echo "Failed to send test results, but continuing..."
          else
            echo "test_results.json not found, skipping..."
          fi
        env:
          backend_api_url: {backend_api_url}
      
      - name: Stop application
        if: always()
        run: pkill -f "node"
"""


def _generate_python_flask_workflow(test_case_path: str, backend_api_url: str) -> str:
	"""Generate workflow for Python Flask projects."""
	return f"""name: API Test

on:
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      
      - name: Start application
        run: |
          echo "Starting Python Flask application..."
          python app.py > app.log 2>&1 &
          APP_PID=$!
          echo "Application started with PID: $APP_PID"
          echo "Waiting 10 seconds for initial startup..."
          sleep 10
          echo "Checking if application process is still running..."
          if ! ps -p $APP_PID > /dev/null; then
            echo "ERROR: Application process died during startup!"
            echo "=== Application Logs ==="
            cat app.log || true
            exit 1
          fi
          echo "Application process is running (PID: $APP_PID)"
        env:
          FLASK_ENV: test
          FLASK_PORT: 5000
      
      - name: Wait for application to be ready
        run: |
          echo "Waiting for application to be ready..."
          timeout=120
          elapsed=0
          while ! curl -f http://localhost:5000/health 2>/dev/null; do
            if [ $elapsed -ge $timeout ]; then
              echo "ERROR: Application failed to start within $timeout seconds"
              echo "=== Checking application status ==="
              ps aux | grep python | grep app.py || true
              echo "=== Checking if port 5000 is listening ==="
              netstat -tlnp | grep 5000 || ss -tlnp | grep 5000 || true
              echo "=== Application Logs (last 50 lines) ==="
              tail -50 app.log || true
              echo "=== Trying to access root endpoint ==="
              curl -v http://localhost:5000/ || true
              exit 1
            fi
            echo "Waiting for application... (elapsed: ${{elapsed}}s)"
            sleep 2
            elapsed=$((elapsed + 2))
          done
          echo "Application is ready! Health check passed."
          echo "=== Application Logs (last 20 lines) ==="
          tail -20 app.log || true
      
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      
      - name: Run API tests
        id: test
        run: |
          node test-runner.js {test_case_path}
      
      - name: Send test results to backend
        if: always()
        run: |
          if [ -f test_results.json ]; then
            echo "Sending test results to backend..."
            REPO_URL="${{{{ github.repository }}}}"
            ORG="${{{{ github.repository_owner }}}}"
            WORKFLOW_RUN_ID="${{{{ github.run_id }}}}"
            WORKFLOW_RUN_URL="${{{{ github.server_url }}}}/${{{{ github.repository }}}}/actions/runs/${{{{ github.run_id }}}}"
            
            # Build JSON payload using jq
            PAYLOAD=$(jq -n \\
              --arg repo_url "https://github.com/$REPO_URL" \\
              --arg org "$ORG" \\
              --arg workflow_run_id "$WORKFLOW_RUN_ID" \\
              --arg workflow_run_url "$WORKFLOW_RUN_URL" \\
              --slurpfile test_results test_results.json \\
              '{{repo_url: $repo_url, org: $org, workflow_run_id: $workflow_run_id, workflow_run_url: $workflow_run_url, test_results: $test_results[0]}}')
            
            curl -X POST "${{{{ env.backend_api_url }}}}/repos/test-results" \\
              -H "Content-Type: application/json" \\
              -d "$PAYLOAD" || echo "Failed to send test results, but continuing..."
          else
            echo "test_results.json not found, skipping..."
          fi
        env:
          backend_api_url: {backend_api_url}
      
      - name: Stop application
        if: always()
        run: pkill -f "python.*app.py"
"""

