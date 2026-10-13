"""Tests fuer Doichain Seal: OIDC-Pruefung, Versiegeln, Index, Abzeichen und Pruefseiten.

Die RPC-Schicht ist die Fake-Node aus test_poe.py, die GitHub-Signaturschluessel werden durch ein lokal
erzeugtes RSA-Paar ersetzt. Es braucht weder Node noch Netz."""

import dataclasses
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# Zuerst test_poe, damit die Testumgebung vor dem Import von config.py gesetzt ist.
from .test_poe import HASH, NEW_TXID, client, node  # noqa: F401 (Fixtures)
from doichain_api import github_oidc, main, quota, seals  # noqa: E402

REPO = "octocat/hello-world"
SHA = "a" * 40

_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_pem = _private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)


def make_token(**overrides) -> str:
    claims = {
        "iss": main.settings.github_oidc_issuer,
        "aud": main.settings.seal_audience,
        "sub": f"repo:{REPO}:ref:refs/tags/v1.2.3",
        "iat": int(time.time()) - 5,
        "exp": int(time.time()) + 300,
        "repository": REPO,
        "repository_owner": "octocat",
        "ref": "refs/tags/v1.2.3",
        "ref_type": "tag",
        "sha": SHA,
        "run_id": "123456",
        "workflow": "Release",
        "event_name": "release",
        "repository_visibility": "public",
    }
    claims.update(overrides)
    return jwt.encode(claims, _private, algorithm="RS256", headers={"kid": "test-key"})


@pytest.fixture(autouse=True)
def local_jwks(monkeypatch):
    """GitHub-Schluesselabruf durch das Testpaar ersetzen."""
    monkeypatch.setattr(github_oidc._jwks, "signing_key", lambda token: _public_pem)


@pytest.fixture(autouse=True)
def fresh_index(monkeypatch, tmp_path):
    """Jeder Test bekommt einen leeren Siegel-Index und leere Kontingente (Settings ist eingefroren,
    deshalb eine Kopie mit anderem StateDirectory in allen Modulen)."""
    fresh = dataclasses.replace(main.settings, state_dir=str(tmp_path))
    for module in (main, quota, seals):
        monkeypatch.setattr(module, "settings", fresh)


def auth(token: str) -> dict:
    return {"Authorization": "Bearer " + token}


# ---------------------------------------------------------------------------
# OIDC
# ---------------------------------------------------------------------------

def test_missing_token_gives_401(node, client):
    response = client.post("/v1/seal/github", json={"hash": HASH})
    assert response.status_code == 401
    assert "Bearer" in response.json()["error"]["message"]
    assert "name_doi" not in node.methods()


def test_wrong_audience_gives_401(node, client):
    response = client.post("/v1/seal/github", json={"hash": HASH}, headers=auth(make_token(aud="something-else")))
    assert response.status_code == 401
    assert "audience" in response.json()["error"]["message"]


def test_expired_token_gives_401(node, client):
    response = client.post("/v1/seal/github", json={"hash": HASH}, headers=auth(make_token(exp=int(time.time()) - 600)))
    assert response.status_code == 401
    assert "expired" in response.json()["error"]["message"]


def test_wrong_issuer_gives_401(node, client):
    response = client.post("/v1/seal/github", json={"hash": HASH}, headers=auth(make_token(iss="https://evil.example")))
    assert response.status_code == 401


def test_token_without_repository_gives_401(node, client):
    response = client.post("/v1/seal/github", json={"hash": HASH}, headers=auth(make_token(repository="")))
    assert response.status_code == 401
    assert "repository" in response.json()["error"]["message"]


def test_api_key_is_not_accepted_as_oidc_token(node, client):
    response = client.post("/v1/seal/github", json={"hash": HASH}, headers={"Authorization": "Bearer test-write-key-0000000000"})
    assert response.status_code == 401
    assert "name_doi" not in node.methods()


# ---------------------------------------------------------------------------
# Versiegeln
# ---------------------------------------------------------------------------

def test_seal_anchors_with_github_origin_in_value(node, client):
    response = client.post("/v1/seal/github", json={"hash": HASH, "filename": "app-1.2.3.tar.gz", "size": 1234}, headers=auth(make_token()))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "anchored"
    assert body["repository"] == REPO
    assert body["ref"] == "v1.2.3"
    assert body["anchoring"]["txid"] == NEW_TXID
    assert body["proof_url"].endswith("/seal/" + HASH)
    assert body["repo_badge_url"].endswith(f"/seal/github/{REPO}/badge.svg")
    assert "[![Doichain Seal](" in body["badge_markdown"]
    assert body["seal"]["file"] == "app-1.2.3.tar.gz"
    assert body["seal"]["size"] == 1234
    assert body["seal"]["anchored_by_this_run"] is True
    doi_calls = [params for method, params in node.calls if method == "name_doi"]
    assert len(doi_calls) == 1
    assert doi_calls[0][0] == "poe/" + HASH
    value = json.loads(doi_calls[0][1])
    assert value["gh"] == {"repo": REPO, "ref": "v1.2.3", "sha": SHA[:12]}
    assert value["file"] == "app-1.2.3.tar.gz"
    assert "size" not in value


def test_seal_counts_quota_per_repository_not_per_ip(node, client):
    for n in range(main.settings.seal_per_repo_day):
        response = client.post("/v1/seal/github", json={"hash": f"{n:064x}"}, headers=auth(make_token()))
        assert response.status_code == 201, response.text
    blocked = client.post("/v1/seal/github", json={"hash": "e" * 64}, headers=auth(make_token()))
    assert blocked.status_code == 429
    assert "repository" in blocked.json()["error"]["message"]
    # Ein anderes Repository von derselben Adresse darf weiter.
    other = client.post("/v1/seal/github", json={"hash": "d" * 64}, headers=auth(make_token(repository="other/repo", sub="repo:other/repo:ref:refs/tags/v1")))
    assert other.status_code == 201, other.text
    # Das Siegel-Kontingent belastet weder die oeffentliche App noch die Schluessel.
    assert quota.usage("testclient")["used_total"] == 0
    assert quota.usage("key:0123456789abcdef")["used_total"] == 0


def test_already_anchored_hash_returns_200_and_records_index(node, client):
    node.add_history("poe/" + HASH, [(1, node.tip - 10, "N1first", "erste")])
    response = client.post("/v1/seal/github", json={"hash": HASH, "filename": "app.zip"}, headers=auth(make_token()))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "already_anchored"
    assert body["proof"]["status"] == "confirmed"
    assert body["seal"]["anchored_by_this_run"] is False
    assert "name_doi" not in node.methods()
    # Kein Kontingent verbraucht
    assert quota.usage(quota.GH_PREFIX + REPO)["used_ip"] == 0


def test_rerun_of_same_workflow_does_not_duplicate_index(node, client):
    first = client.post("/v1/seal/github", json={"hash": HASH}, headers=auth(make_token()))
    assert first.status_code == 201
    node.add_history("poe/" + HASH, [(1, node.tip - 1, "N1first", "erste")])
    second = client.post("/v1/seal/github", json={"hash": HASH}, headers=auth(make_token()))
    assert second.status_code == 200
    assert len(seals.for_repo(REPO)) == 1


def test_failed_anchoring_releases_repo_quota(node, client, monkeypatch):
    async def failing(method, *params, **kwargs):
        if method == "name_doi":
            raise main.RPCError(-6, "Insufficient funds")
        return await original(method, *params, **kwargs)

    original = node.call
    monkeypatch.setattr(main.rpc, "call", failing)
    response = client.post("/v1/seal/github", json={"hash": HASH}, headers=auth(make_token()))
    assert response.status_code == 402
    assert quota.usage(quota.GH_PREFIX + REPO)["used_ip"] == 0
    assert seals.for_repo(REPO) == []


def test_branch_ref_uses_branch_name_as_tag(node, client):
    response = client.post("/v1/seal/github", json={"hash": HASH}, headers=auth(make_token(ref="refs/heads/main", ref_type="branch")))
    assert response.status_code == 201
    assert response.json()["ref"] == "main"
    assert seals.for_repo(REPO)[0]["tag"] == "main"


# ---------------------------------------------------------------------------
# Lesen, Abzeichen, Seiten
# ---------------------------------------------------------------------------

def test_repo_json_lists_seals_with_status(node, client):
    client.post("/v1/seal/github", json={"hash": HASH, "filename": "a.zip"}, headers=auth(make_token()))
    node.add_history("poe/" + HASH, [(1, node.tip - 3, "N1first", "erste")])
    response = client.get(f"/v1/seal/github/{REPO}")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["latest"]["tag"] == "v1.2.3"
    assert body["latest"]["proof"]["status"] == "confirmed"
    assert body["repo_badge_url"].endswith("/badge.svg")


def test_repo_json_unknown_repo_is_empty(node, client):
    response = client.get("/v1/seal/github/nobody/nothing")
    assert response.status_code == 200
    assert response.json()["count"] == 0
    assert response.json()["latest"] is None


def test_invalid_github_name_gives_400(node, client):
    assert client.get("/v1/seal/github/bad%20owner/repo").status_code == 400
    assert client.get("/seal/github/-bad/repo/badge.svg").status_code == 400


def test_hash_json_reports_verified_origin(node, client):
    value = json.dumps({"v": 1, "alg": "sha256", "hash": HASH, "ts": "2026-10-13T00:00:00Z", "file": "a.zip", "gh": {"repo": REPO, "ref": "v1.2.3", "sha": SHA[:12]}}, separators=(",", ":"))
    node.add_history("poe/" + HASH, [(1, node.tip - 3, "N1first", "x")])
    node.names["poe/" + HASH]["value"] = value
    node.histories["poe/" + HASH][0]["value"] = value
    response = client.get("/v1/seal/" + HASH)
    assert response.status_code == 200
    body = response.json()
    assert body["origin"] == {"repo": REPO, "ref": "v1.2.3", "sha": SHA[:12], "verified": True}
    assert body["repo_page_url"].endswith("/seal/github/" + REPO)


def test_hash_json_without_origin(node, client):
    node.add_history("poe/" + HASH, [(1, node.tip - 3, "N1first", "x")])
    body = client.get("/v1/seal/" + HASH).json()
    assert body["origin"] is None
    assert "repo_page_url" not in body


def test_badge_for_unknown_hash_is_grey(node, client):
    response = client.get(f"/seal/{HASH}/badge.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert "not sealed" in response.text
    assert seals.COLORS["grey"] in response.text
    assert "max-age=300" in response.headers["cache-control"]


def test_badge_for_confirmed_hash_shows_block(node, client):
    node.add_history("poe/" + HASH, [(1, 5000, "N1first", "x")])
    response = client.get(f"/seal/{HASH}/badge.svg")
    assert "block 5000" in response.text
    assert seals.COLORS["green"] in response.text
    assert "max-age=3600" in response.headers["cache-control"]


def test_badge_for_pending_hash_is_yellow(node, client):
    node.pending["poe/" + HASH] = [{"txid": NEW_TXID, "op": "name_doi", "address": "N1", "value": "{}"}]
    response = client.get(f"/seal/{HASH}/badge.svg")
    assert "pending" in response.text
    assert seals.COLORS["yellow"] in response.text
    assert "max-age=60" in response.headers["cache-control"]


def test_repo_badge_shows_tag_and_block(node, client):
    client.post("/v1/seal/github", json={"hash": HASH}, headers=auth(make_token()))
    node.add_history("poe/" + HASH, [(1, 7000, "N1first", "x")])
    response = client.get(f"/seal/github/{REPO}/badge.svg")
    assert "v1.2.3 · block 7000" in response.text
    empty = client.get("/seal/github/nobody/nothing/badge.svg")
    assert "no seals yet" in empty.text


def test_badge_escapes_xml():
    svg = seals.badge_svg("a<b", 'c"&d', "green")
    assert "a&lt;b" in svg and "c&quot;&amp;d" in svg
    assert "a<b" not in svg


def test_hash_page_shows_origin_and_og_tags(node, client):
    value = json.dumps({"v": 1, "alg": "sha256", "hash": HASH, "ts": "2026-10-13T00:00:00Z", "file": "a.zip", "gh": {"repo": REPO, "ref": "v1.2.3", "sha": SHA[:12]}}, separators=(",", ":"))
    node.add_history("poe/" + HASH, [(1, 5000, "N1first", "x")])
    node.names["poe/" + HASH]["value"] = value
    node.histories["poe/" + HASH][0]["value"] = value
    response = client.get("/seal/" + HASH)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    page = response.text
    assert 'property="og:image"' in page and "/seal/og.png" in page
    assert "Sealed in block 5000" in page
    assert f"https://github.com/{REPO}/releases/tag/v1.2.3" in page
    assert "verifying a GitHub Actions OIDC token" in page
    assert "sha256sum a.zip" in page


def test_hash_page_unknown_hash(node, client):
    page = client.get("/seal/" + HASH).text
    assert "Not sealed" in page
    assert "Nothing with this hash has been anchored yet" in page


def test_hash_page_escapes_chain_values(node, client):
    evil = json.dumps({"v": 1, "alg": "sha256", "hash": HASH, "ts": "x", "file": "<script>alert(1)</script>", "gh": {"repo": "x/<img src=x onerror=alert(1)>", "ref": "v1", "sha": "abc"}})
    node.add_history("poe/" + HASH, [(1, 5000, "N1first", "x")])
    node.names["poe/" + HASH]["value"] = evil
    node.histories["poe/" + HASH][0]["value"] = evil
    page = client.get("/seal/" + HASH).text
    assert "<script>" not in page
    assert "<img src=x" not in page
    assert "&lt;script&gt;" in page


def test_repo_page_lists_releases(node, client):
    client.post("/v1/seal/github", json={"hash": HASH, "filename": "a.zip"}, headers=auth(make_token()))
    node.add_history("poe/" + HASH, [(1, 5000, "N1first", "x")])
    page = client.get(f"/seal/github/{REPO}").text
    assert "All sealed files" in page
    assert "a.zip" in page
    assert f"/seal/github/{REPO}/badge.svg" in page
    assert "block 5000" in page


def test_index_page_and_stats(node, client):
    client.post("/v1/seal/github", json={"hash": HASH}, headers=auth(make_token()))
    stats = client.get("/v1/seal/stats").json()
    assert stats["seals"] == 1 and stats["repositories"] == 1 and stats["seals_today_utc"] == 1
    page = client.get("/seal").text
    assert "Doichain Seal" in page
    assert "id-token: write" in page
    assert REPO in page
    assert client.get("/seal/og.png").headers["content-type"] == "image/png"
    assert client.get("/seal/favicon.svg").status_code == 200


def test_openapi_lists_seal_tag(client):
    schema = client.get("/openapi.json").json()
    assert "/v1/seal/github" in schema["paths"]
    assert any(t["name"] == "Seal" for t in schema["tags"])
