# DPostBackend

Python backend project scaffold.

## 环境准备

1) 创建/激活虚拟环境（Windows PowerShell）

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
```

2) 安装依赖

```powershell
pip install -r requirements.txt
```

## 运行（FastAPI + Uvicorn）

开发模式自动重载：
```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

访问：
- 健康检查: `http://127.0.0.1:8000/health`
- 文档: `http://127.0.0.1:8000/docs`

前端联调（CORS）：已允许以下来源
- `http://localhost:5173`、`http://127.0.0.1:5173`
- `http://localhost:3000`、`http://127.0.0.1:3000`
如需其它来源，请在 `app/main.py` 的 `allow_origins` 中追加。

## 环境变量
在项目根目录创建 `.env` 文件（已在 `.gitignore` 中忽略），至少包含：
```
GITHUB_PAT=ghp_xxx_your_personal_access_token
```
PAT 需要具备 `public_repo`（公共仓库）或 `repo`（含私有仓库）权限。

可选：设置日志等级
```
LOG_LEVEL=DEBUG
```
可选值：DEBUG/INFO/WARNING/ERROR/CRITICAL（默认 INFO）

可选：设置后端 API URL（用于 GitHub Actions 发送测试结果）
```
BACKEND_API_URL=https://your-backend-domain.com
```
如果不设置，默认为 `http://localhost:8000`

### 数据库

默认使用 SQLite（`./data/cache.db`）缓存仓库 fork 请求的响应，首次启动会自动建表。
如需自定义路径，可设置环境变量：
```
DATABASE_URL=sqlite:///./data/cache.db
```
也可切换为其他 SQLAlchemy 支持的数据库。

### 测试 GitHub PAT

使用内置脚本快速校验你的 PAT 是否有效、拥有哪些 scopes：
```powershell
.\.venv\Scripts\Activate.ps1
python .\scripts\test_pat.py            # 默认读取 .env 中的 GITHUB_PAT
python .\scripts\test_pat.py --token "ghp_xxx"  # 或者直接传入
```
输出会显示 login、X-OAuth-Scopes、速率限制等信息。

### 更新 Workflow 文件

使用内置脚本更新 fork 仓库中的 GitHub Actions workflow 文件：
```powershell
.\.venv\Scripts\Activate.ps1
# 基本用法
python .\scripts\update_workflow.py --repo-url https://github.com/owner/repo --tech-stack springboot_maven

# 带组织名称
python .\scripts\update_workflow.py --repo-url https://github.com/owner/repo --org myorg --tech-stack nodejs_express

# 指定自定义 API URL
python .\scripts\update_workflow.py --repo-url https://github.com/owner/repo --tech-stack python_flask --api-url http://localhost:8000

# 输出 JSON 格式
python .\scripts\update_workflow.py --repo-url https://github.com/owner/repo --tech-stack springboot_maven --json
```

**参数说明**：
- `--repo-url` (必需): GitHub 仓库 URL
- `--tech-stack` (必需): 技术栈类型，可选值：`springboot_maven`、`nodejs_express`、`python_flask`
- `--org` (可选): 组织名称
- `--backend-api-url` (可选): 后端 API URL
- `--api-url` (可选): API 基础 URL，默认为 `http://localhost:8000` 或环境变量 `API_BASE_URL`
- `--timeout` (可选): 请求超时时间（秒），默认 30.0
- `--json` (可选): 以 JSON 格式输出结果

**注意**：
- 此脚本会使用最新的 `workflow_generator.py` 逻辑重新生成 workflow 文件
- 需要先 fork 仓库（`POST /repos/fork`）
- 即使 workflow 文件已存在，也会强制更新

## API

### Fork 仓库
- 路径: `POST /repos/fork`
- 请求体:
```json
{
  "repo_url": "https://github.com/owner/repo",
  "org": "optional-org-name"
}
```
- 成功响应:
```json
{
  "status": "ok",
  "data": { "...": "GitHub API response" }
}
```
- 失败响应: `400`（请求不合法）或 `502`（GitHub API 错误信息）

### 提交测试用例
- 路径: `POST /repos/test`
- 请求方式: `multipart/form-data`
- 请求参数:
  - `repo_url` (string, required): GitHub 仓库地址
  - `org` (string, optional): 组织名称
  - `tech_stack` (string, required): 技术栈，可选值：
    - `springboot_maven`
    - `nodejs_express`
    - `python_flask`
  - `test_case_file` (file, required): DSL JSON 格式的测试用例文件
- 成功响应（立即返回，不等待 GitHub 操作）:
```json
{
  "status": "ok",
  "message": "Test case saved successfully. Pushing to GitHub and triggering tests in background...",
  "file_path": "./data/test_cases/owner_repo_org.json",
  "repo_full_name": "owner/repo",
  "org": "org-name",
  "tech_stack": "springboot_maven",
  "note": "GitHub push and workflow trigger are running in background. Check GitHub Actions for test results."
}
```
- 失败响应:
  - `400`: 请求参数不合法（无效的 tech_stack、无效的仓库 URL、无效的 JSON 文件）
  - `404`: 仓库未在数据库中找到（需要先 fork）
  - `500`: 服务器内部错误

**注意**: 
- 测试用例文件会保存在 `./data/test_cases/` 目录下，文件名格式为 `{owner}_{repo}_{org}.json`（如果提供了 org）或 `{owner}_{repo}.json`（如果未提供 org）。如果文件已存在，会被覆盖。
- **自动推送（后台执行）**: 保存测试用例后，系统会在后台自动将测试用例和 GitHub Actions 工作流推送到 fork 的仓库，并触发测试运行。API 会立即返回，不等待 GitHub 操作完成。
- 如果推送失败（例如 fork 信息不存在），测试用例仍会保存在本地，但不会推送到 GitHub。错误信息会记录在日志中。

### 更新测试用例
- 路径: `PUT /repos/test`
- 请求方式: `multipart/form-data`
- 请求参数:
  - `repo_url` (string, required): GitHub 仓库地址
  - `org` (string, optional): 组织名称
  - `tech_stack` (string, required): 技术栈，可选值：
    - `springboot_maven`
    - `nodejs_express`
    - `python_flask`
  - `test_case_file` (file, required): DSL JSON 格式的测试用例文件
- 成功响应（立即返回，不等待 GitHub 操作）:
```json
{
  "status": "ok",
  "message": "Test case updated successfully. Pushing to GitHub and triggering tests in background...",
  "file_path": "./data/test_cases/owner_repo_org.json",
  "repo_full_name": "owner/repo",
  "org": "org-name",
  "tech_stack": "springboot_maven",
  "note": "GitHub push and workflow trigger are running in background. Check GitHub Actions for test results."
}
```
- 失败响应:
  - `400`: 请求参数不合法（无效的 tech_stack、无效的仓库 URL、无效的 JSON 文件）
  - `404`: 仓库未在数据库中找到（需要先 fork）或测试用例文件不存在（需要先使用 POST /repos/test 提交）
  - `500`: 服务器内部错误

**注意**: 
- 此接口用于更新已存在的测试用例文件。如果测试用例文件不存在，请先使用 `POST /repos/test` 接口提交。
- **自动推送（后台执行）**: 更新测试用例后，系统会在后台自动将更新的测试用例和 GitHub Actions 工作流推送到 fork 的仓库，并触发测试运行。API 会立即返回，不等待 GitHub 操作完成。
- 如果推送失败（例如 fork 信息不存在），测试用例仍会保存在本地，但不会推送到 GitHub。错误信息会记录在日志中。

### 删除仓库
- 路径: `DELETE /repos`
- 请求体:
```json
{
  "repo_url": "https://github.com/owner/repo",
  "org": "optional-org-name"
}
```
- 成功响应:
```json
{
  "status": "ok",
  "message": "Repository deleted from local cache successfully",
  "repo_full_name": "owner/repo",
  "org": "org-name",
  "deleted_from": {
    "database": true,
    "test_case_file": true
  }
}
```
- 失败响应:
  - `400`: 请求参数不合法（无效的仓库 URL）
  - `404`: 仓库未在数据库中找到
  - `500`: 服务器内部错误

**注意**: 
- 此接口仅删除本地缓存（数据库中的缓存记录和测试用例文件），**不会删除 GitHub 上的仓库**
- 删除操作不可逆，请谨慎使用

### 同步 Fork（Sync fork to upstream）

- 路径: `POST /repos/sync-upstream`
- 请求体 (application/json):
```json
{
  "repo_url": "https://github.com/owner/repo",
  "org": "optional-org-name",
  "branch": "main"
}
```
- 说明:
  - 由本服务使用配置在 `.env` 中的 `GITHUB_PAT`（服务账号）对 fork 仓库执行 GitHub 的 `merge-upstream` 操作，尝试将上游仓库的变更合并到 fork 的指定分支。
  - 要求仓库之前已由本服务 fork 并存在本地缓存（也就是已调用过 `POST /repos/fork` 并成功），否则接口会返回 `404`。
  - `branch` 为可选字段，默认 `main`。

- 成功响应:
  - `200`: 同步成功（GitHub 返回的具体 JSON 会被透传）
  - `202`: 已接受，GitHub 已启动异步同步任务（可能在后台执行）

- 失败响应:
  - `400`: 请求不合法（比如无效的 `repo_url`）
  - `404`: 本服务未找到该仓库的 fork 缓存记录（请先 fork）
  - `502`: 代理到 GitHub 时出现错误（GitHub 返回 4xx/5xx）
  - `500`: 服务器内部错误

- 示例请求（PowerShell + curl）:
```powershell
$body = @{ repo_url = "https://github.com/original-owner/repo"; org = ""; branch = "main" } | ConvertTo-Json
curl -X POST "http://127.0.0.1:8000/repos/sync-upstream" -H "Content-Type: application/json" -d $body
```

- 注意事项:
  - `GITHUB_PAT` 需要具有对 fork 仓库进行合并/写操作的权限（通常需要 `repo` 范围）。
  - GitHub 的 `merge-upstream` 可能返回 `200`（已完成）或 `202`（已接受并在后台处理）。本服务会把 GitHub 的响应内容原样返回给调用者。
  - 如果希望在找不到 fork 信息时自动发起 fork 并等待结果，请告诉我，我可以把接口改为先执行 `fork_repository`。

### 推送测试用例和 GitHub Actions 配置
- 路径: `POST /repos/push-test`
- 请求体:
```json
{
  "repo_url": "https://github.com/owner/repo",
  "org": "optional-org-name",
  "tech_stack": "springboot_maven",
  "backend_api_url": "http://localhost:8000"
}
```
- 请求参数:
  - `repo_url` (string, required): 原始 GitHub 仓库地址
  - `org` (string, optional): 组织名称
  - `tech_stack` (string, required): 技术栈，可选值：
    - `springboot_maven`
    - `nodejs_express`
    - `python_flask`
  - `backend_api_url` (string, optional): 后端 API URL，用于接收测试结果。如果不提供，将从环境变量 `BACKEND_API_URL` 读取，默认为 `http://localhost:8000`
- 成功响应:
```json
{
  "status": "ok",
  "message": "Test case and workflow pushed successfully",
  "repo_full_name": "owner/repo",
  "fork_full_name": "fork_owner/repo",
  "org": "org-name",
  "tech_stack": "springboot_maven",
  "files_pushed": [
    "test_case.json",
    ".github/workflows/api-test.yml"
  ]
}
```
- 失败响应:
  - `400`: 请求参数不合法（无效的 tech_stack、无效的仓库 URL）
  - `404`: 仓库未在数据库中找到（需要先 fork）或测试用例文件不存在（需要先使用 POST /repos/test 提交）
  - `500`: 服务器内部错误（推送文件失败）

**注意**: 
- 此接口会将测试用例文件（`test_case.json`）和 GitHub Actions 工作流文件（`.github/workflows/api-test.yml`）推送到 fork 的仓库中
- 需要先 fork 仓库（`POST /repos/fork`）和提交测试用例（`POST /repos/test`）
- GitHub Actions 工作流会根据技术栈自动生成，包含启动应用、运行测试和发送结果到后端的步骤

### 更新 Workflow 文件
- 路径: `PUT /repos/update-workflow`
- 请求体:
```json
{
  "repo_url": "https://github.com/owner/repo",
  "org": "optional-org-name",
  "tech_stack": "springboot_maven",
  "backend_api_url": "http://localhost:8000"
}
```
- 请求参数:
  - `repo_url` (string, required): GitHub 仓库地址
  - `org` (string, optional): 组织名称
  - `tech_stack` (string, required): 技术栈，可选值：
    - `springboot_maven`
    - `nodejs_express`
    - `python_flask`
  - `backend_api_url` (string, optional): 后端 API URL，用于接收测试结果。如果不提供，将从环境变量 `BACKEND_API_URL` 读取，默认为 `http://localhost:8000`
- 成功响应:
```json
{
  "status": "ok",
  "message": "Workflow updated successfully",
  "repo_full_name": "owner/repo",
  "fork_full_name": "fork_owner/repo",
  "org": "org-name",
  "tech_stack": "springboot_maven",
  "workflow_updated": true
}
```
- 失败响应:
  - `400`: 请求参数不合法（无效的 tech_stack、无效的仓库 URL、缺少 tech_stack）
  - `404`: 仓库未在数据库中找到（需要先 fork）
  - `500`: 服务器内部错误（更新 workflow 文件失败）

**注意**: 
- 此接口会使用最新的 `workflow_generator.py` 逻辑重新生成并更新 fork 仓库中的 GitHub Actions workflow 文件
- 需要先 fork 仓库（`POST /repos/fork`）
- 即使 workflow 文件已存在，也会强制更新
- 如果 workflow 文件不存在，会创建新文件
- 修改 `workflow_generator.py` 后，可以使用此接口批量更新所有仓库的 workflow 文件

### 获取最新测试结果
- 路径: `GET /repos/test-results`
- 查询参数:
  - `repo_url` (string, required): GitHub 仓库 URL，例如 `https://github.com/owner/repo`
  - `org` (string, optional): 组织名称
- 成功响应:
```json
{
  "status": "ok",
  "filename": "DPostRobot_hello-spring-boot_DPostRobot_20251116_173514.json",
  "data": {
    "repo_url": "https://github.com/DPostRobot/hello-spring-boot",
    "repo_full_name": "DPostRobot/hello-spring-boot",
    "org": "DPostRobot",
    "workflow_run_id": "19403625453",
    "workflow_run_url": "https://github.com/...",
    "received_at": "2025-11-16T17:35:14.123456",
    "test_results": {
      "testCaseFile": "test_case.json",
      "config": {...},
      "total": 16,
      "passed": 13,
      "failed": 3,
      "successRate": 81.25,
      "timestamp": "2025-11-16T17:35:14.000Z",
      "tests": [...]
    }
  }
}
```
- 失败响应:
  - `400`: 请求参数不合法（无效的仓库 URL）
  - `404`: 未找到匹配的测试结果

**注意**: 
- 此接口返回指定仓库的最新测试结果文件（完整内容）
- 按文件修改时间倒序查找，返回第一个匹配的结果
- 如果提供了 `org` 参数，会匹配相同组织的结果；如果不提供，会匹配所有组织的结果

### 获取单个测试结果文件
- 路径: `GET /repos/test-results/{filename}`
- 路径参数:
  - `filename` (string, required): 测试结果文件名，例如 `DPostRobot_hello-spring-boot_DPostRobot_20251116_173514.json`
- 成功响应:
```json
{
  "status": "ok",
  "filename": "DPostRobot_hello-spring-boot_DPostRobot_20251116_173514.json",
  "data": {
    "repo_url": "https://github.com/DPostRobot/hello-spring-boot",
    "repo_full_name": "DPostRobot/hello-spring-boot",
    "org": "DPostRobot",
    "workflow_run_id": "19403625453",
    "workflow_run_url": "https://github.com/...",
    "received_at": "2025-11-16T17:35:14.123456",
    "test_results": {
      "testCaseFile": "test_case.json",
      "config": {...},
      "total": 16,
      "passed": 13,
      "failed": 3,
      "successRate": 81.25,
      "timestamp": "2025-11-16T17:35:14.000Z",
      "tests": [...]
    }
  }
}
```
- 失败响应:
  - `400`: 文件名不合法（包含路径遍历字符）
  - `404`: 测试结果文件不存在
  - `500`: 服务器内部错误（文件读取失败或 JSON 解析失败）

**注意**: 
- 此接口返回完整的测试结果文件内容
- 文件名必须精确匹配，不支持通配符
- 为防止路径遍历攻击，文件名中不能包含 `..`、`/`、`\` 等字符

## 常用命令

- 激活虚拟环境：
  ```powershell
  .\\.venv\\Scripts\\Activate.ps1
  ```

- 退出虚拟环境：
  ```powershell
  deactivate
  ```

- 冻结依赖：
  ```powershell
  pip freeze > requirements.txt
  ```

### Test: 同步 Fork 脚本

项目提供了一个简单的测试脚本用于调用 `POST /repos/sync-upstream` 接口，位于 `scripts/test_sync_upstream.py`。

依赖：
```powershell
pip install requests python-dotenv
```

运行示例（PowerShell）：
```powershell
# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 调用脚本（替换 repo_url）
python .\scripts\test_sync_upstream.py --repo-url https://github.com/original-owner/repo --branch main
```

脚本会优先读取根目录下的 `.env` 中的 `BACKEND_API_URL` 作为后端地址，亦可通过 `--base-url` 参数覆盖。

## Git

初始化仓库：
```powershell
git init -b main
git add .
git commit -m "chore: initialize Python backend scaffold"
```


