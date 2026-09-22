"""Pagination checks for the optional member listing endpoint."""

import pytest


def test_member_list_is_empty_by_default(client):
    response = client.get("/members")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


def test_member_list_pages_keep_total_and_id_order(client, make_member):
    members = [make_member() for _ in range(3)]

    first = client.get("/members?limit=2&offset=0")
    assert first.status_code == 200
    assert first.json() == {
        "items": members[:2], "total": 3, "limit": 2, "offset": 0,
    }

    last = client.get("/members?limit=2&offset=2")
    assert last.status_code == 200
    assert last.json() == {
        "items": members[2:], "total": 3, "limit": 2, "offset": 2,
    }

    beyond = client.get("/members?limit=2&offset=3")
    assert beyond.status_code == 200
    assert beyond.json() == {"items": [], "total": 3, "limit": 2, "offset": 3}


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "limit=abc", "offset=-1", "offset=abc"])
def test_member_list_rejects_invalid_pagination(client, query):
    assert client.get(f"/members?{query}").status_code == 422


def test_member_list_accepts_maximum_limit(client, make_member):
    member = make_member()
    response = client.get("/members?limit=100")
    assert response.status_code == 200
    assert response.json() == {"items": [member], "total": 1, "limit": 100, "offset": 0}
