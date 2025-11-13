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
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
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
  - `test_case_file` (file, required): OpenAPI 规范的测试用例 JSON 文件
- 成功响应:
```json
{
  "status": "ok",
  "message": "Test case saved successfully",
  "file_path": "./data/test_cases/owner_repo_org.json",
  "repo_full_name": "owner/repo",
  "org": "org-name",
  "tech_stack": "springboot_maven"
}
```
- 失败响应:
  - `400`: 请求参数不合法（无效的 tech_stack、无效的仓库 URL、无效的 JSON 文件）
  - `404`: 仓库未在数据库中找到（需要先 fork）
  - `500`: 服务器内部错误

**注意**: 测试用例文件会保存在 `./data/test_cases/` 目录下，文件名格式为 `{owner}_{repo}_{org}.json`（如果提供了 org）或 `{owner}_{repo}.json`（如果未提供 org）。如果文件已存在，会被覆盖。

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
  - `test_case_file` (file, required): OpenAPI 规范的测试用例 JSON 文件
- 成功响应:
```json
{
  "status": "ok",
  "message": "Test case updated successfully",
  "file_path": "./data/test_cases/owner_repo_org.json",
  "repo_full_name": "owner/repo",
  "org": "org-name",
  "tech_stack": "springboot_maven"
}
```
- 失败响应:
  - `400`: 请求参数不合法（无效的 tech_stack、无效的仓库 URL、无效的 JSON 文件）
  - `404`: 仓库未在数据库中找到（需要先 fork）或测试用例文件不存在（需要先使用 POST /repos/test 提交）
  - `500`: 服务器内部错误

**注意**: 此接口用于更新已存在的测试用例文件。如果测试用例文件不存在，请先使用 `POST /repos/test` 接口提交。

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

## Git

初始化仓库：
```powershell
git init -b main
git add .
git commit -m "chore: initialize Python backend scaffold"
```


