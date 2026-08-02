# Shared contracts

这里存放由 Python 合约导出的 normalize 和 pattern JSON Schema，供 API、Worker 和离线诊断工具共享。权威定义位于 `services/backend/src/plush_pattern_studio/contracts` 的 Pydantic 模型；不要直接编辑生成的 Schema。

Regenerate after an intentional contract change:

```powershell
npm run contracts:export
```

Changing field semantics requires a new `schemaVersion` or `algorithmVersion`.

验证合约改动：

```powershell
npm run contracts:export
python -m pytest services/backend/tests/test_pattern_pipeline.py services/backend/tests/test_geometry_normalize.py -q
```
