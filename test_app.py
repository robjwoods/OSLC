import pytest
from app import app, requirements_db

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def test_index_route(client):
    rv = client.get("/")
    assert rv.status_code == 200
    assert b"<html" in rv.data or b"<!DOCTYPE html" in rv.data

def test_create_requirement(client):
    rv = client.post("/api/requirements", json={
        "title": "Test Req",
        "description": "Test Desc",
        "type": "Functional",
        "state": "New"
    })
    assert rv.status_code == 201
    data = rv.get_json()
    assert data["title"] == "Test Req"
    assert data["state"] == "New"
    assert data["id"].startswith("REQ-")

def test_create_requirement_missing_title(client):
    rv = client.post("/api/requirements", json={
        "description": "No title"
    })
    assert rv.status_code == 400
    data = rv.get_json()
    assert "error" in data

def test_list_requirements(client):
    rv = client.get("/api/requirements")
    assert rv.status_code == 200
    data = rv.get_json()
    assert isinstance(data, list)

def test_update_requirement(client):
    # First, create a requirement
    rv = client.post("/api/requirements", json={
        "title": "Update Req",
        "description": "Desc"
    })
    req_id = rv.get_json()["id"]
    # Now, update it
    rv2 = client.put(f"/api/requirements/{req_id}", json={
        "title": "Updated Title",
        "state": "Active"
    })
    assert rv2.status_code == 200
    data = rv2.get_json()
    assert data["title"] == "Updated Title"
    assert data["state"] == "Active"

def test_delete_requirement(client):
    rv = client.post("/api/requirements", json={
        "title": "Delete Req"
    })
    req_id = rv.get_json()["id"]
    rv2 = client.delete(f"/api/requirements/{req_id}")
    assert rv2.status_code == 200
    data = rv2.get_json()
    assert data["message"] == "Deleted"
    # Should not exist now
    rv3 = client.delete(f"/api/requirements/{req_id}")
    assert rv3.status_code == 404

def test_add_link(client):
    # Create two requirements
    rv1 = client.post("/api/requirements", json={"title": "Source"})
    rv2 = client.post("/api/requirements", json={"title": "Target"})
    src_id = rv1.get_json()["id"]
    tgt_id = rv2.get_json()["id"]
    # Add link
    rv3 = client.post(f"/api/requirements/{src_id}/links", json={
        "target": tgt_id,
        "type": "satisfies"
    })
    assert rv3.status_code == 201
    data = rv3.get_json()
    assert any(l["target"] == tgt_id for l in data["links"])

def test_traceability(client):
    rv = client.get("/api/traceability")
    assert rv.status_code == 200
    data = rv.get_json()
    assert isinstance(data, list)