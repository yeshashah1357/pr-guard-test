from app.models import Role


def test_viewer_cannot_register_repositories(client, viewer):
    response = client.post("/api/repos", json={"full_name": "acme/api"}, headers=viewer)
    assert response.status_code == 403


def test_admin_registers_repository_once(client, admin, viewer):
    assert client.post("/api/repos", json={"full_name": "acme/api"}, headers=admin).status_code == 201
    assert client.post("/api/repos", json={"full_name": "acme/api"}, headers=admin).status_code == 409
    repos = client.get("/api/repos", headers=viewer).json()
    assert [r["full_name"] for r in repos] == ["acme/api"]


def test_invalid_repository_name_is_rejected(client, admin):
    response = client.post("/api/repos", json={"full_name": "../../etc"}, headers=admin)
    assert response.status_code == 422


def test_role_change_applies_to_existing_token(client, admin, make_user):
    headers = make_user("rev@example.com", Role.viewer)
    me = client.get("/api/auth/me", headers=headers).json()
    client.patch(f"/api/auth/users/{me['id']}/role", json={"role": "admin"}, headers=admin)
    # Same token, new role: roles are read from the DB on every request.
    assert client.post("/api/repos", json={"full_name": "acme/web"}, headers=headers).status_code == 201


def test_only_admin_changes_roles_and_cannot_self_demote(client, admin, viewer):
    admin_id = client.get("/api/auth/me", headers=admin).json()["id"]
    viewer_id = client.get("/api/auth/me", headers=viewer).json()["id"]
    assert (
        client.patch(f"/api/auth/users/{admin_id}/role", json={"role": "viewer"}, headers=viewer).status_code
        == 403
    )
    assert (
        client.patch(f"/api/auth/users/{admin_id}/role", json={"role": "viewer"}, headers=admin).status_code
        == 400
    )
    assert client.patch("/api/auth/users/999/role", json={"role": "viewer"}, headers=admin).status_code == 404
    response = client.patch(f"/api/auth/users/{viewer_id}/role", json={"role": "reviewer"}, headers=admin)
    assert response.json()["role"] == "reviewer"
