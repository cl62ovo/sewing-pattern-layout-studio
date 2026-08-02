# Plush Pattern Studio

Plush Pattern Studio 是一个面向低弹短毛绒的实验性纸样工作台：将受约束的玩偶描述转换为 Meshy 3D 模型，再经过确定性的 GLB 规范化、分片、展开、质量检查和 A4 PDF 导出。所有结果都只是几何验证结果，不代表已经通过真实布料或实缝验证。

当前仓库包含：

- `apps/web`：React + Vite 工作台，包含项目创建、任务状态、GLB 预览和纸样报告。
- `services/backend`：FastAPI API、SQLite/对象存储适配器和 Python Worker。
- `packages/contracts`：由 Python Pydantic 合约导出的共享 JSON Schema。
- `index.html` 与 `apps/web/public/legacy`：旧版 `Nest & Cut` 排版演示，作为视觉和行为参考。

## 当前范围

已实现的本地闭环是：文字描述与成品高度 -> 结构化规格 -> Meshy 任务 -> GLB 规范化 -> 纸样 SVG/PDF -> 质量报告。默认缝份为 7 mm，纸样最多 12 片，合格导出要求平均形变不超过 3%、配对缝边长度差不超过 0.5%，并通过网格和 PDF 检查。

目前尚未实现：Google 登录、参考图上传、版本编辑/文字修改、真实二维排版 API、云端 PostgreSQL/Redis 部署和三视图 PNG。`Nest & Cut` 仍通过 iframe 加载旧版静态演示。

## 技术统计

截至 2026-08-02，按 Git 跟踪文件统计：

| 项目 | 数量 |
| --- | ---: |
| 代码类文件（前端、后端、工具、静态页面） | 55 个文件 / 12,275 行 |
| 全部可统计文本文件 | 75 个文件 / 19,106 行 |
| 前端与后端测试 | 11 个文件 / 781 行 |
| FastAPI 路由 | 12 个 |
| 共享合约 Schema | 4 个文件 / 697 行 |

代码类文件包含根目录静态 demo 和已提交的前端构建资源；全部文本文件还包含 JSON、Markdown 和 TOML 等配置/文档。统计不包含 `node_modules`、`.venv`、未跟踪的 `dist`、诊断输出、GLB 和其他二进制资产；行数为文件当前物理行数，不代表有效逻辑行数。

## 本地安装

要求：Node.js 20.19+、Python 3.11+。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".\services\backend[dev]"
npm install
npm run db:migrate
```

后端默认使用 `./var/plush-pattern-studio.db` 和 `./var/objects`，无需 `.env` 即可运行。需要调用真实供应商时，在仓库根目录创建 `.env`，使用 `OPENROUTER_API_KEY` 和 `MESHY_API_KEY` 等后端设置；密钥不得使用 `VITE_` 前缀，也不得提交到 Git。

## 启动

在仓库根目录分别打开三个终端：

```powershell
npm run dev:web
npm run dev:api
npm run dev:worker
```

访问地址：Web `http://localhost:8001`，API `http://localhost:8000`，Swagger 文档 `http://localhost:8000/docs`。Windows 也可以直接运行 `start-dev.bat`，脚本会激活 `.venv` 并启动全部服务。

如果没有配置供应商密钥，Web 和 API 仍可启动，但生成任务无法调用 OpenRouter/Meshy。测试使用 fake provider，不需要真实密钥。

## API 入口

当前已实现的主要接口：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/health/live` | 存活检查 |
| `GET` | `/api/health/ready` | 数据库和对象存储检查 |
| `GET` | `/api/capabilities` | 查看供应商能力与 Meshy 余额 |
| `GET/POST` | `/api/projects` | 列出或创建本地项目 |
| `GET` | `/api/projects/{id}` | 查看项目和版本资产 |
| `POST` | `/api/versions/{id}/model-jobs` | 创建模型任务，支持幂等键 |
| `POST` | `/api/jobs/{id}/resume` | 恢复已有供应商任务 |
| `GET` | `/api/jobs/{id}` | 查看任务状态 |
| `POST` | `/api/versions/{id}/accept-model` | 接受模型并启动纸样任务 |
| `GET` | `/api/versions/{id}/pattern` | 查看纸样报告 |
| `GET` | `/api/versions/{id}/quality-report` | 查看质量门槛结果 |
| `GET` | `/api/assets/{id}` | 下载本地资产 |

## 几何 CLI

```powershell
npm run geometry -- .\path\model.glb --height-mm 240 `
  --seam-allowance-mm 7 `
  --output-directory .\diagnostics\pattern `
  --output-json .\diagnostics\report.json
```

CLI 会输出规范化 GLB、诊断 JSON、纸样 SVG，以及仅在全部门槛通过时输出的矢量 PDF。失败结果仍会保留诊断 SVG，便于定位网格、分片、展开或质量检查问题。

## 验证与合约

```powershell
npm run build
npm run test:web
python -m pytest services/backend/tests -q
```

合约发生有意变更后重新导出 Schema：

```powershell
npm run contracts:export
```

更多产品边界、架构和待办事项见 [docs/DESIGN.md](docs/DESIGN.md)、[docs/ROADMAP.md](docs/ROADMAP.md) 和 [docs/PROMPTS.md](docs/PROMPTS.md)。
