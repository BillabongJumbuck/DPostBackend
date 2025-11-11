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


