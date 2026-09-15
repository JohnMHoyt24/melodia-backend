def test_create_and_get_artist(client):
    create_response = client.post("/artists", json={"name": "Boards of Canada"})
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["name"] == "Boards of Canada"
    assert created["musicbrainz_id"] is None

    get_response = client.get(f"/artists/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Boards of Canada"


def test_list_artists(client):
    client.post("/artists", json={"name": "Aphex Twin"})
    client.post("/artists", json={"name": "Autechre"})

    response = client.get("/artists")
    assert response.status_code == 200
    names = [artist["name"] for artist in response.json()]
    assert names == ["Aphex Twin", "Autechre"]


def test_get_missing_artist_404(client):
    response = client.get("/artists/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
