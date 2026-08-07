#!/usr/bin/env python3
"""API tests for Go-Tone Marketplace using Python with httpx.
Hits the live server at localhost:8080.
"""
import httpx, json, sys, time

BASE = "http://localhost:8080"
PREFIX = f"test{int(time.time())}"
passed = 0
failed = 0

def test(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        print(f"  ✗ {name}")

def api(method, path, json_data=None, headers=None):
    """Return (status_code, response_json)."""
    r = httpx.request(method, f"{BASE}{path}", json=json_data, headers=headers)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {}

print("=== Auth Flow Tests ===")

# 1. Register
code, body = api("POST", "/api/auth/register",
    {"email": f"{PREFIX}@gotone.com", "password": "secret123", "name": "Py3 Test"})
token = body.get("access_token", "")
test("register: 200", code == 200)
test("register: has access_token", bool(token))
test("register: tier defaults to free", body.get("user", {}).get("tier") == "free")

# 2. Duplicate registration
code, _ = api("POST", "/api/auth/register",
    {"email": f"{PREFIX}@gotone.com", "password": "secret123", "name": "Py3 Test"})
test("duplicate register: 409", code == 409)

# 3. Login correct
code, _ = api("POST", "/api/auth/login",
    {"email": f"{PREFIX}@gotone.com", "password": "secret123"})
test("login: 200", code == 200)

# 4. Login wrong password
code, _ = api("POST", "/api/auth/login",
    {"email": f"{PREFIX}@gotone.com", "password": "WRONG"})
test("login wrong password: 401", code == 401)

# 5. Login nonexistent
code, _ = api("POST", "/api/auth/login",
    {"email": "ghost@nowhere.com", "password": "x"})
test("login nonexistent: 401", code == 401)

# 6. Profile with valid token
auth = {"Authorization": f"Bearer {token}"}
code, body = api("GET", "/api/user/profile", headers=auth)
test("profile with token: 200", code == 200)
test("profile tier is free", body.get("tier") == "free")

# 7. Profile without token
code, _ = api("GET", "/api/user/profile")
test("profile no token: 401", code == 401)

# 8. Profile with bad token
code, _ = api("GET", "/api/user/profile",
    headers={"Authorization": "Bearer garbage.token"})
test("profile bad token: 401", code == 401)

print("\n=== Tier Access: Free User ===")

# 9. Free user: premium game blocked
code, _ = api("POST", "/api/library/dragon-pull/purchase", headers=auth)
test("free user: premium game → 402", code == 402)

# 10. Free user: can add free game
code, _ = api("POST", "/api/library/rhythm-pull/purchase", headers=auth)
test("free user: free game → 200", code == 200)

# 11. Library shows owned games
code, body = api("GET", "/api/library", headers=auth)
owned_slugs = [g["slug"] for g in body.get("owned", [])]
test("library: contains rhythm-pull", "rhythm-pull" in owned_slugs)

# 12. Submit score
code, _ = api("POST", "/api/games/rhythm-pull/score",
    json_data={"weight": 20, "score": 1500, "reps": 10, "meters": 50.5},
    headers=auth)
test("free user: can submit score", code == 200)

print("\n=== Tier Access: Paid User (Subscribed) ===")

# To test paid-tier access, we directly upgrade a user in the DB
# since the API doesn't expose tier management yet.
import sqlite3, os
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "data", "marketplace.db")

# Register a fresh user for paid-tier tests
code, body = api("POST", "/api/auth/register",
    {"email": f"{PREFIX}-paid@gotone.com", "password": "secret123", "name": "Paid User"})
paid_token = body.get("access_token", "")
paid_auth = {"Authorization": f"Bearer {paid_token}"}

# Upgrade their tier directly in the DB
conn = sqlite3.connect(db_path)
user_id = body["user"]["id"]
conn.execute("UPDATE users SET tier = 'pro' WHERE id = ?", (user_id,))
conn.commit()
conn.close()

# Now re-login to get a token with the updated tier
code, body = api("POST", "/api/auth/login",
    {"email": f"{PREFIX}-paid@gotone.com", "password": "secret123"})
paid_token = body.get("access_token", "")
paid_auth = {"Authorization": f"Bearer {paid_token}"}

test("paid user: tier is pro", body.get("user", {}).get("tier") == "pro")

# 13. Paid user can purchase premium game
code, _ = api("POST", "/api/library/dragon-pull/purchase", headers=paid_auth)
test("paid user: premium game → 200", code == 200)

# 14. Paid user can also add free games
code, _ = api("POST", "/api/library/rhythm-pull/purchase", headers=paid_auth)
test("paid user: free game → 200", code == 200)

# 15. Library shows both free and premium games
code, body = api("GET", "/api/library", headers=paid_auth)
owned_slugs = [g["slug"] for g in body.get("owned", [])]
test("paid library: has dragon-pull (premium)", "dragon-pull" in owned_slugs)
test("paid library: has rhythm-pull (free)", "rhythm-pull" in owned_slugs)

print("\n=== Public Access ===")

code, body = api("GET", "/api/games")
test("public: browse games → 200", code == 200)
test("public: 8 games", len(body) == 8)

code, _ = api("GET", "/api/leaderboard/dragon-pull")
test("public: leaderboard → 200", code == 200)

code, _ = api("GET", "/api/library")
test("public: library requires auth (401)", code == 401)

code, _ = api("POST", "/api/library/rhythm-pull/purchase")
test("public: purchase requires auth (401)", code == 401)

print(f"\n{'='*30}")
print(f"Results: {passed} passed, {failed} failed, {passed+failed} total")
if failed == 0:
    print("✅ ALL TESTS PASSED")
else:
    print(f"❌ {failed} TESTS FAILED")
sys.exit(0 if failed == 0 else 1)
