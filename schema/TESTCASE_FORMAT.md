# 📘 API 自动化测试用例格式说明（DSL 文档）

> 版本：v1.0  
> 作者：DPost
> 说明：本文档定义 API 自动化测试所使用的 JSON 格式规范。

---

# 目录

1. [简介](#简介)  
2. [总体结构](#总体结构)  
3. [字段说明](#字段说明)  
   - [config](#config)
   - [variables](#variables)
   - [tests](#tests)
   - [step](#step)
   - [request](#request)
   - [expect](#expect)
   - [extract](#extract)
4. [变量替换规则](#变量替换规则)
5. [完整示例](#完整示例)
6. [JSON Schema](#json-schema)
7. [常见错误](#常见错误)

---

# 简介

本 JSON DSL 用于定义 Web API 的自动化测试流程。  
用户需提供一个符合本格式规范的 `testcases.json` 文件，然后平台将自动运行所有 API 测试步骤并生成测试报告。

该 DSL 支持：

- 链式依赖步骤（提取变量 → 下个请求使用）
- 深度 JSON 校验
- Header / Query / Body 自定义
- 自定义断言
- 多测试集（tests）

---

# 总体结构

测试文件的整体 JSON 结构如下：

```json
{
  "config": { },
  "variables": { },
  "tests": [ ]
}
````

---

# 字段说明

## config

```json
"config": {
  "baseUrl": "http://localhost:3000",
  "timeout": 5000,
  "retries": 1,
  "stopOnFailure": false
}
```

| 字段            | 类型      | 说明             |
| ------------- | ------- | -------------- |
| baseUrl       | string  | 所有相对 URL 的基准路径 |
| timeout       | number  | 单个请求默认超时时间     |
| retries       | number  | 失败时重试次数        |
| stopOnFailure | boolean | 遇到第一个失败是否中断    |

---

## variables

```json
"variables": {
  "username": "alice",
  "password": "1234"
}
```

变量使用格式：

```
{{username}}
```

---

# tests

每个测试集包含多个步骤：

```json
"tests": [
  {
    "name": "User Workflow",
    "steps": []
  }
]
```

| 字段    | 说明   |
| ----- | ---- |
| name  | 测试名称 |
| steps | 步骤数组 |

---

# step

```json
{
  "name": "Login",
  "request": { },
  "expect": { },
  "extract": { },
  "delay": 1000
}
```

| 字段      | 必填 | 说明          |
| ------- | -- | ----------- |
| name    | 是  | 步骤名称        |
| request | 是  | 请求定义        |
| expect  | 否  | 响应断言        |
| extract | 否  | 从响应中提取变量    |
| delay   | 否  | 步骤结束后延迟（毫秒） |

---

# request

```json
"request": {
  "method": "POST",
  "url": "/login",
  "headers": {
    "Content-Type": "application/json"
  },
  "query": { "debug": true },
  "body": {
    "username": "{{username}}",
    "password": "{{password}}"
  },
  "timeout": 5000
}
```

| 字段      | 类型     | 说明                                |
| ------- | ------ | --------------------------------- |
| method  | string | GET / POST / PUT / DELETE / PATCH |
| url     | string | 请求 URL（可含变量）                      |
| headers | object | 请求头                               |
| query   | object | 查询参数                              |
| body    | any    | 请求体                               |
| timeout | number | 覆盖全局 timeout                      |

---

# expect

```json
"expect": {
  "status": 200,
  "json": {
    "username": "alice"
  },
  "contains": "success",
  "custom": "response.json.data.length > 0"
}
```

| 字段       | 类型     | 说明           |
| -------- | ------ | ------------ |
| status   | number | HTTP 状态码     |
| headers  | object | 响应头断言        |
| json     | object | 深度 JSON 匹配   |
| contains | string | 响应体必须包含字符串   |
| custom   | string | 自定义 JS 表达式断言 |

---

# extract

通过 JSONPath 提取字段：

```json
"extract": {
  "token": "$.data.token",
  "userId": "$..id"
}
```

之后可通过：

```
{{token}}
```

使用。

---

# 变量替换规则

以下位置均可使用变量：

* URL
* Headers
* Query
* Body
* expect.json

格式：

```
{{variableName}}
```

变量来源：

1. 全局 variables
2. extract 生成的变量

---

# 完整示例

```json
{
  "config": {
    "baseUrl": "http://localhost:3000",
    "timeout": 5000
  },
  "variables": {
    "username": "alice",
    "password": "1234"
  },
  "tests": [
    {
      "name": "User Workflow",
      "steps": [
        {
          "name": "Register",
          "request": {
            "method": "POST",
            "url": "/register",
            "body": {
              "username": "{{username}}",
              "password": "{{password}}"
            }
          },
          "expect": { "status": 201 }
        },
        {
          "name": "Login",
          "request": {
            "method": "POST",
            "url": "/login",
            "body": {
              "username": "{{username}}",
              "password": "{{password}}"
            }
          },
          "extract": {
            "token": "$.token",
            "userId": "$..id"
          },
          "expect": { "status": 200 }
        },
        {
          "name": "Get User Info",
          "request": {
            "method": "GET",
            "url": "/user/{{userId}}",
            "headers": {
              "Authorization": "Bearer {{token}}"
            }
          },
          "expect": {
            "status": 200,
            "json": {
              "username": "{{username}}"
            }
          }
        }
      ]
    }
  ]
}
```

---

# JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "config": {
      "type": "object",
      "properties": {
        "baseUrl": { "type": "string" },
        "timeout": { "type": "number" },
        "retries": { "type": "number" },
        "stopOnFailure": { "type": "boolean" }
      },
      "additionalProperties": false
    },
    "variables": {
      "type": "object",
      "additionalProperties": {
        "type": ["string", "number", "boolean"]
      }
    },
    "tests": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "steps"],
        "properties": {
          "name": { "type": "string" },
          "steps": {
            "type": "array",
            "minItems": 1,
            "items": {
              "type": "object",
              "required": ["name", "request"],
              "properties": {
                "name": { "type": "string" },
                "delay": { "type": "number" },
                "request": {
                  "type": "object",
                  "required": ["method", "url"],
                  "properties": {
                    "method": {
                      "type": "string",
                      "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"]
                    },
                    "url": { "type": "string" },
                    "headers": {
                      "type": "object",
                      "additionalProperties": { "type": ["string", "number", "boolean"] }
                    },
                    "query": {
                      "type": "object",
                      "additionalProperties": { "type": ["string", "number", "boolean"] }
                    },
                    "body": {},
                    "timeout": { "type": "number" }
                  },
                  "additionalProperties": false
                },
                "expect": {
                  "type": "object",
                  "properties": {
                    "status": { "type": "number" },
                    "headers": { "type": "object" },
                    "json": {},
                    "contains": { "type": "string" },
                    "custom": { "type": "string" }
                  },
                  "additionalProperties": false
                },
                "extract": {
                  "type": "object",
                  "additionalProperties": { "type": "string" }
                }
              },
              "additionalProperties": false
            }
          }
        },
        "additionalProperties": false
      }
    }
  },
  "required": ["tests"],
  "additionalProperties": false
}
```

---

# 常见错误

| 错误                                       | 原因                 |
| ---------------------------------------- | ------------------ |
| `tests is required`                      | 缺少 tests 字段        |
| `method must be one of allowed values`   | method 不合法         |
| `status should be number`                | expect.status 类型错误 |
| `steps must NOT have fewer than 1 items` | steps 为空           |

---

# 结束

如有更多 DSL 扩展需求，可继续联系维护者。


