# Plush Pattern Studio

Experimental tooling for turning a constrained plush mesh into validated sewing-pattern geometry. The current M0 build provides a React technical workbench, FastAPI health checks, a standalone worker process, versioned data contracts, and a deterministic GLB normalization CLI.

The original static layout demo remains at the repository root as a visual and behavior reference. New source code lives under `apps/` and `services/`.

## Local setup

Requirements: Node.js 20.19+ and Python 3.11+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".\services\backend[dev]"
npm install
npm run db:migrate
```

Do not create a real `.env` until local overrides are needed. When required, base it on `.env.example`; all secrets are read by the Python services and must never use a `VITE_` prefix.

## Run

Use separate terminals from the repository root:

```powershell
npm run dev:web
npm run dev:api
npm run dev:worker
```

The web app runs at `http://localhost:8001`, the API at `http://localhost:8000`, and API documentation at `http://localhost:8000/docs`.

For Windows, run `start-dev.bat` from the repository root to activate the local virtual environment and start the web app, API, and worker together.

## Geometry CLI

```powershell
npm run geometry -- .\path\model.glb --height-mm 240 `
  --output-glb .\diagnostics\normalized.glb `
  --output-json .\diagnostics\report.json
```

The command performs GLB container validation, SHA-256 hashing, scene transform baking, Y-axis scaling to millimeters, and deterministic mesh diagnostics. Segmentation, flattening, scoring, and PDF generation deliberately return `NOT_IMPLEMENTED` in M0.

## Verify

```powershell
npm run build
npm test
```

All generated patterns remain experimental and are not evidence of physical sewability.
