# Shared contracts

Generated normalize and pattern JSON Schemas shared by the browser, API, worker, and offline diagnostics. Python Pydantic models in `services/backend/src/plush_pattern_studio/contracts` are authoritative.

Regenerate after an intentional contract change:

```powershell
npm run contracts:export
```

Changing field semantics requires a new `schemaVersion` or `algorithmVersion`.
