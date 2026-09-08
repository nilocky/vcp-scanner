from __future__ import annotations
import os, sys, tempfile, unittest.mock as mock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

import app.main as main
from app.db.cache import BarCache

client = TestClient(main.app)


def test_saved_scans_crud() -> None:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    cache = BarCache(path)
    with mock.patch.object(main, "_cache", cache):
        res = client.get("/api/v1/scans")
        assert res.status_code == 200 and res.json() == []

        res = client.post("/api/v1/scans", json={
            "name": "Tight setups",
            "filters": {"min_contractions": 3, "min_tightness": 8.0, "min_ai_score": 80, "include_premature": True},
        })
        assert res.status_code == 200, res.text
        scan = res.json()
        assert scan["id"] == 1
        assert scan["filters"]["min_ai_score"] == 80
        assert scan["name"] == "Tight setups"

        res = client.get("/api/v1/scans")
        assert len(res.json()) == 1

        res = client.delete("/api/v1/scans/1")
        assert res.status_code == 200 and res.json() == {"ok": True}
        assert client.get("/api/v1/scans").json() == []

        res = client.delete("/api/v1/scans/99")
        assert res.status_code == 404


if __name__ == "__main__":
    test_saved_scans_crud()
    print("saved scans crud passed")
