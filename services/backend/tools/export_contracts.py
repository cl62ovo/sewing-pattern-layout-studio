import json
from pathlib import Path

from plush_pattern_studio.contracts.pipeline import (
    GeometryPipelineReport,
    PatternPipelineReport,
)


def main() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    output_directory = repository_root / "packages" / "contracts"
    output_directory.mkdir(parents=True, exist_ok=True)
    contracts = {
        "geometry-pipeline.schema.json": GeometryPipelineReport,
        "pattern-pipeline.schema.json": PatternPipelineReport,
    }
    for file_name, model in contracts.items():
        schema = model.model_json_schema(by_alias=True)
        (output_directory / file_name).write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
