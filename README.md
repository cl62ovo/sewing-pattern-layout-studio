# Plush Pattern Studio

Experimental tooling for turning a constrained plush mesh into validated sewing-pattern geometry. The application provides a React workbench, FastAPI API, standalone worker, persistent project jobs, versioned data contracts, and a deterministic geometry pipeline from GLB normalization through A4 PDF export.

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
  --seam-allowance-mm 7 `
  --output-directory .\diagnostics\pattern `
  --output-json .\diagnostics\report.json
```

The command validates and normalizes the GLB to millimeters, creates bounded seam-chart candidates, flattens disk pieces with LSCM, walks paired seam chains, adds seam allowance, and computes the final quality report. It writes `normalized.glb` and `pattern.svg`; `pattern.pdf` is emitted only when all gates pass:

- no more than 12 pieces
- area-weighted mean distortion no greater than 3%
- paired seam-chain mismatch no greater than 0.5%
- no flipped triangles, invalid boundaries, or unpaired seams
- valid A4 vector PDF with a 50 x 50 mm calibration square

The same pipeline runs after a model is accepted in the web app. The worker persists the report, SVG, and eligible PDF; failed geometry remains available as a clearly marked diagnostic SVG.

## Verify

```powershell
npm run build
npm test
```

Regenerate both shared JSON Schemas after an intentional contract change:

```powershell
npm run contracts:export
```

All generated patterns remain experimental and are not evidence of physical sewability.
