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


