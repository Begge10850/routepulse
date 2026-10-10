import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).parents[1]

def test_generated_data_contract():
    metadata = json.loads((ROOT / "public/data/metadata.json").read_text())
    assert metadata["coordinateSystem"] == "EPSG:4326"
    assert len(metadata["generatedFiles"]) == 5
    for filename, facts in metadata["generatedFiles"].items():
        payload = json.loads((ROOT / "public/data" / filename).read_text())
        assert facts["routes"] == len(payload["routes"]) > 0
        for route in payload["routes"]:
            assert len(route["path"]) >= 2
            assert all(math.isfinite(value) for point in route["path"] for value in point)
            assert all(10 <= point[0] <= 16 and 50 <= point[1] <= 55 for point in route["path"])
