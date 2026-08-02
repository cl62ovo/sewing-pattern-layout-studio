import json
from pathlib import Path

from plush_pattern_studio.contracts.pipeline import GeometryPipelineReport


def main() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    output_path = repository_root / "packages" / "contracts" / "geometry-pipeline.schema.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    schema = GeometryPipelineReport.model_json_schema(by_alias=True)
    output_path.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
