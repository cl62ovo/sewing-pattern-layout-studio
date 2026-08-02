# Plush Pattern Studio

Plush Pattern Studio 是一个面向低弹短毛绒的实验性纸样工作台。仓库里有两条并行工作流：

- **Pattern Studio**：从玩偶描述和成品高度开始，生成 3D 候选模型，再构建、检查并导出纸样。
- **Nest & Cut**：从已有的纸样图开始，设置布料和纸张尺寸，识别裁片并预览排版。

两条工作流目前都可以从同一个本地 Web 应用进入，但它们的实现阶段不同：Pattern Studio 连接本地 FastAPI/Worker，Nest & Cut 仍是通过 iframe 加载的旧版静态演示。所有结果都只是实验性或几何验证结果，不代表已经通过真实布料或实缝验证。

## For beginners

### 先选工作流

| 你手上有什么 | 从哪里开始 | 你会得到什么 |
| --- | --- | --- |
| 只有一个玩偶想法，想让系统帮你生成纸样 | **Pattern Studio** | 3D 候选模型、纸样 SVG/PDF、质量报告 |
| 已经有纸样图片，想安排到一块布上 | **Nest & Cut** | 布料比例预览、裁片识别建议和排版工作区 |

### Pattern Studio：从想法到纸样

1. 在仓库根目录运行安装步骤和本地服务（见[本地安装](#本地安装)与[启动](#启动)）。
2. 打开 Web 地址，保持默认的 `Pattern Studio` 标签页。
3. 创建项目，填写名称、玩偶描述、成品高度和缝份。
4. 创建规格后启动模型生成；模型完成后先在 3D 预览中检查，再接受模型。
5. 等待分片、展开和质量检查完成。通过检查后下载 1:1 A4 PDF 或 SVG。

适合从简单、圆润的单体玩偶开始，例如一个主体、两只连接的耳朵或一条简单尾巴。当前默认材料是低弹短毛绒，默认缝份是 7 mm。生成失败时，先查看质量报告和诊断信息，不要把数字通过当成真实试缝通过。

### Nest & Cut：从纸样图到布料布局

在顶部切换到 `Nest & Cut`，按这个顺序操作：

1. 选择 `Plain fabric` 或 `Patterned fabric`。有条纹、格纹或印花时选择后者，并按页面提示单独提供布料图案。
2. 输入布料宽度和可用长度，选择 `cm` 或 `in`。
3. 上传一张包含全部裁片的完整纸样图，支持 JPG/PNG，最大 20 MB。应使用白底、深色且闭合的裁剪轮廓，不要上传布料照片代替纸样图。
4. 设置纸样页的真实尺寸：`A4`、`A3` 或 `Custom`，再选择纵向/横向和单位。
5. 使用 `Find sewing pieces` 生成首轮裁片识别；轮廓太淡时提高敏感度，误识别小图形时降低敏感度，漏片时使用 `Add missed piece` 修正。
6. 检查裁片轮廓、数量、旋转和间距，再继续布局。屏幕上的尺寸比例用于预览，不能替代实际打印校准。

Nest & Cut 当前是独立的静态演示：它不会把布局结果保存到 Pattern Studio 项目，也还没有接入真实二维排版 API。需要持久化项目、生成纸样或查看几何质量报告时，应回到 `Pattern Studio`。

### 最短启动方式

要求 Node.js 20.19+ 和 Python 3.11+。在仓库根目录打开 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".\services\backend[dev]"
npm install
npm run dev
```

然后访问 Web `http://localhost:8001`。Windows 也可以直接运行 `start-dev.bat`，它会启动 Web、API 和 Worker。

没有供应商密钥时，页面和测试仍可启动；但 Pattern Studio 的真实 OpenRouter/Meshy 生成任务不能完成。Nest & Cut 的静态演示不依赖这些密钥。

## For pros

### 两条入口的实现边界

`apps/web/src/App.tsx` 将两个功能作为 peer tabs 管理：

- `Pattern Studio` 渲染 `PatternStudio`，调用 `/api/projects`、模型任务、接受模型和纸样报告接口。
- `Nest & Cut` 渲染 `/legacy/index.html` iframe。根目录 `index.html` 是源静态页面；`tools/sync-legacy.mjs` 在 dev/build 前复制并清理到 `apps/web/public/legacy`。

仓库的主要目录：

- `apps/web`：React + Vite 工作台、3D 预览和标签页壳。
- `services/backend`：FastAPI API、SQLite/对象存储适配器和 Python Worker。
- `packages/contracts`：由 Python Pydantic 合约导出的共享 JSON Schema。
- `index.html`：Nest & Cut legacy 源页面；不是 Pattern Studio 的 React 页面。

Pattern Studio 的本地闭环为：

```text
文字描述与成品高度
  -> 结构化规格 -> Meshy 任务 -> GLB 规范化
  -> 自动分片与展开 -> 几何质量检查 -> SVG/PDF 与报告
```

默认质量门槛是最多 12 片、平均形变不超过 3%、配对缝边长度差不超过 0.5%，并通过网格和 PDF 检查。Nest & Cut 目前只提供前端演示层，不共享这套后端版本、资产或质量门槛。

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
