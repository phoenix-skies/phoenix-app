import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("APP_VERSION", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ERROR_RATE", "0")
    import app as app_module

    importlib.reload(app_module)
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json["status"] == "ok"


def test_readyz(client):
    assert client.get("/readyz").status_code == 200


def test_list_products_seeded(client):
    r = client.get("/api/products")
    assert r.status_code == 200
    assert len(r.json) == 6
    assert {"id", "name", "category", "price", "stock"} <= set(r.json[0])


def test_filter_by_category(client):
    r = client.get("/api/products?category=Audio")
    assert [p["name"] for p in r.json] == ["Phoenix Buds Pro"]


def test_get_product_and_404(client):
    assert client.get("/api/products/1").json["id"] == 1
    assert client.get("/api/products/999").status_code == 404


def test_cart_flow(client):
    r = client.post("/api/cart/s1", json={"product_id": 3, "quantity": 2})
    assert r.status_code == 201
    cart = client.get("/api/cart/s1").json
    assert cart["items"][0]["quantity"] == 2
    assert cart["total"] == 7998.0


def test_cart_validation(client):
    assert client.post("/api/cart/s1", json={"product_id": "x"}).status_code == 400
    assert client.post("/api/cart/s1", json={"product_id": 999}).status_code == 404


def test_metrics_exposed(client):
    client.get("/api/products")
    body = client.get("/metrics").data.decode()
    assert "phoenix_http_requests_total" in body
    assert 'version="test"' in body


def test_error_rate_simulation(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "e.db"))
    monkeypatch.setenv("ERROR_RATE", "1.0")
    import app as app_module

    importlib.reload(app_module)
    c = app_module.app.test_client()
    assert c.get("/api/products").status_code == 500
    assert c.get("/healthz").status_code == 200  # probes stay green: only the canary analysis catches it
