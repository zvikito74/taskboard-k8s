import pytest

from app import MemoryStore, create_app


@pytest.fixture
def client():
    return create_app(MemoryStore()).test_client()


def add(client, title):
    return client.post("/api/tasks", json={"title": title})


def test_probes(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").get_json() == {"status": "ready"}


def test_readyz_reports_database_failure():
    class BrokenStore(MemoryStore):
        def ready(self):
            raise ConnectionError("database is down")

    client = create_app(BrokenStore()).test_client()
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.get_json()["reason"] == "ConnectionError"
    # liveness must stay green even when the database is down
    assert client.get("/healthz").status_code == 200


def test_database_error_returns_503():
    class BrokenStore(MemoryStore):
        def list(self):
            raise ConnectionError("database is down")

    client = create_app(BrokenStore()).test_client()
    response = client.get("/api/tasks")
    assert response.status_code == 503
    assert "error" in response.get_json()
    assert client.get("/nope").status_code == 404  # ordinary HTTP errors are untouched


def test_add_and_list(client):
    response = add(client, "  Write the Dockerfile  ")
    assert response.status_code == 201
    assert response.get_json()["title"] == "Write the Dockerfile"
    assert response.get_json()["status"] == "todo"
    assert len(client.get("/api/tasks").get_json()) == 1


def test_rejects_bad_titles(client):
    assert add(client, "").status_code == 400
    assert add(client, "   ").status_code == 400
    assert add(client, "x" * 121).status_code == 400
    assert client.post("/api/tasks", data="not json").status_code == 400


def test_move_task_between_columns(client):
    task_id = add(client, "Deploy").get_json()["id"]
    response = client.patch(f"/api/tasks/{task_id}", json={"status": "doing"})
    assert response.get_json()["status"] == "doing"
    assert client.patch(f"/api/tasks/{task_id}", json={"status": "finished"}).status_code == 400


def test_rename_task(client):
    task_id = add(client, "Old").get_json()["id"]
    assert client.patch(f"/api/tasks/{task_id}", json={"title": "New"}).get_json()["title"] == "New"
    assert client.patch(f"/api/tasks/{task_id}", json={"title": ""}).status_code == 400
    assert client.patch(f"/api/tasks/{task_id}", json={}).status_code == 400


def test_missing_task(client):
    assert client.patch("/api/tasks/99", json={"status": "done"}).status_code == 404
    assert client.delete("/api/tasks/99").status_code == 404


def test_delete(client):
    task_id = add(client, "Temporary").get_json()["id"]
    assert client.delete(f"/api/tasks/{task_id}").status_code == 204
    assert client.get("/api/tasks").get_json() == []
