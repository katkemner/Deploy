"""Smoke tests for the ManagerFit web app, using an isolated temp store."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from managerfit.app import create_app
from managerfit.storage import Store


@pytest.fixture
def client(tmp_path):
    store = Store(tmp_path / "store.json")
    app = create_app(store=store)
    app.config.update(TESTING=True)
    with app.test_client() as client:
        client._store = store
        yield client


def test_index_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"ManagerFit" in resp.data


def test_create_manager_and_view_profile(client):
    resp = client.post(
        "/assess/manager",
        data={"name": "Sarah Johnson", "role": "Senior PM", "dim_pace": "5", "bf_openness": "4"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Sarah Johnson" in resp.data
    assert len(client._store.list_managers()) == 1


def test_full_fit_flow(client):
    m = client.post("/assess/manager", data={"name": "Sarah", "dim_pace": "5"})
    manager_token = m.headers["Location"].rstrip("/").split("/")[-1]
    c = client.post("/assess/candidate", data={"name": "Alex", "dim_pace": "1"})
    candidate_token = c.headers["Location"].rstrip("/").split("/")[-1]

    resp = client.get(f"/fit/{manager_token}/{candidate_token}")
    assert resp.status_code == 200
    assert b"Areas to discuss" in resp.data
    assert b"Sarah" in resp.data and b"Alex" in resp.data


def test_missing_profile_404(client):
    assert client.get("/manager/nope").status_code == 404
    assert client.get("/fit/nope/nope").status_code == 404
