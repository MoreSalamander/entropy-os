"""Reaching a dispensed copy from where the viewer actually is.

The bug these guard is not exotic: a container bound to loopback is correct,
and the address of a loopback container handed to a hosted visitor points at
that visitor's own laptop. Everything here is about the difference between an
address that is accurate and one that is usable.
"""

from __future__ import annotations

import pytest

from entropy_os.dispensed import HOP_BY_HOP, Copy, Registry, _rebase_html, public_path


def test_a_copy_is_addressed_by_path_not_by_origin():
    """A path is correct on a laptop, on the hosted face, and behind whatever
    hostname either is using — without this code learning any of them."""
    assert public_path("abc123") == "/dispensed/abc123/"
    assert not public_path("abc123").startswith("http")


def test_the_loopback_origin_stays_on_the_machine():
    copy = Copy(container_id="abc", port=61234)
    assert copy.origin == "http://127.0.0.1:61234"
    # …and is never what a viewer is handed.
    assert copy.origin not in public_path(copy.container_id)


def test_the_registry_forgets_a_returned_copy():
    """A route to a container that has been thrown away is worse than no
    route: it fails as though the face were broken."""
    reg = Registry()
    reg.add(Copy(container_id="abc", port=1))
    assert reg.get("abc") is not None
    reg.drop("abc")
    assert reg.get("abc") is None


def test_html_gets_a_base_so_relative_links_resolve():
    out = _rebase_html(b"<html><head><title>x</title></head><body>hi</body></html>",
                       "/dispensed/abc/")
    assert b'<base href="/dispensed/abc/">' in out
    # inserted after <head>, so it precedes anything that might use it
    assert out.index(b"<base") < out.index(b"<title>")


def test_a_document_without_a_head_still_gets_a_base():
    out = _rebase_html(b"<p>fragment</p>", "/dispensed/abc/")
    assert out.startswith(b'<base href="/dispensed/abc/">')


def test_hop_by_hop_headers_are_not_forwarded():
    """Forwarding these across a proxy boundary is how a body arrives
    truncated or double-encoded."""
    for h in ("content-length", "content-encoding", "transfer-encoding",
              "connection", "upgrade"):
        assert h in HOP_BY_HOP


# --------------------------------------------------------------------------- #
# the route itself
# --------------------------------------------------------------------------- #

@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    from entropy_os.app import create_app

    from .conftest import fake_execute
    return TestClient(create_app(data_dir=tmp_path, execute=fake_execute()))


def test_an_unknown_copy_is_a_404_that_explains_itself(client):
    """A restarted face has an empty registry, and a viewer holding an old
    link deserves to know that rather than seeing a bare error."""
    r = client.get("/dispensed/nope/", follow_redirects=False)
    assert r.status_code == 404
    assert "returned" in r.json()["detail"] or "restarted" in r.json()["detail"]


def test_a_copy_that_stopped_answering_blames_the_copy_not_the_face(client):
    """The container is gone but the route remains. The viewer gets 502 with
    the reason, so nobody goes looking for a fault in the front door."""
    # Port 9 is discard: registered, routable, and nothing will answer.
    client.app.state.dispensed.add(Copy(container_id="ghost", port=9))
    r = client.get("/dispensed/ghost/", follow_redirects=False)
    assert r.status_code == 502
    assert "dispensed copy" in r.json()["detail"]


def test_the_proxy_does_not_reach_copies_it_was_not_given(client):
    """Routing is by registered container id, not by anything the caller
    supplies about where to connect — there is no host or port in the URL to
    tamper with."""
    r = client.get("/dispensed/..%2F..%2Fetc/", follow_redirects=False)
    assert r.status_code == 404
