def test_health_check(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_register_login_me(client):
    res = client.post("/api/auth/register", json={
        "email": "tester@cactuscreatives.com", "password": "password123", "full_name": "Tester",
    })
    assert res.status_code == 201
    assert res.json()["role"] == "admin"  # first user becomes admin

    res = client.post("/api/auth/login", json={
        "email": "tester@cactuscreatives.com", "password": "password123",
    })
    assert res.status_code == 200
    tokens = res.json()
    assert "access_token" in tokens and "refresh_token" in tokens

    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert res.status_code == 200
    assert res.json()["email"] == "tester@cactuscreatives.com"


def test_login_wrong_password(client):
    client.post("/api/auth/register", json={
        "email": "user2@cactuscreatives.com", "password": "password123",
    })
    res = client.post("/api/auth/login", json={
        "email": "user2@cactuscreatives.com", "password": "wrongpass",
    })
    assert res.status_code == 401


def test_protected_route_requires_auth(client):
    res = client.get("/api/datasets")
    assert res.status_code == 401
