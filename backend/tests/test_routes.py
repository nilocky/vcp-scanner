"""Route-order regression: literal /vcp/scan must not be shadowed by /vcp/{symbol}."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_scan_routes_not_shadowed_by_symbol_param() -> None:
    """Both /vcp/scan and /vcp/ai/scan must resolve to their handlers, not {symbol}."""
    for path in ("/api/v1/vcp/scan", "/api/v1/vcp/ai/scan"):
        res = client.get(path)
        assert res.status_code == 200, (path, res.status_code, res.text)


if __name__ == "__main__":
    test_scan_routes_not_shadowed_by_symbol_param()
    print("route-order regression passed")