"""Reaching a dispensed copy from wherever the viewer actually is.

A dispensed container binds to loopback on the machine that runs it, which is
correct — a disposable copy of someone's generated code has no business
listening on a public interface. The consequence is that its address is
`http://127.0.0.1:<port>`, and handing that to a visitor of a hosted face
points them at their OWN laptop. The codebase already names this trap
exactly once, in `engine_client.describe_location`: "accurate and useless to
a visitor".

So the front door proxies. A copy is reached at a path on the origin the
viewer is already talking to, and the loopback address never leaves the
machine. Locally that changes nothing; hosted it is the difference between a
feature and a broken link.

WHAT THIS CANNOT DO, stated because it will be met rather than read. Serving
an app under a path prefix works when the app builds its own URLs relatively.
An app that assumes it owns the root — FastAPI's `/docs` fetching
`/openapi.json`, a Next.js bundle requesting `/_next/...` — will ask for
those at the origin root and miss. HTML responses get a `<base>` tag so
relative links resolve, and redirects are rewritten, but an absolute path
compiled into a JavaScript bundle cannot be fixed from out here. The honest
shape of that limit: the proxy is how you SEE what was made. A generated app
that needs to own the root needs its own hostname, which is a routing
decision, not a code one.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from fastapi import HTTPException
from fastapi.responses import Response

# Headers that describe the hop, not the payload. Forwarding them across a
# proxy boundary is how you get a truncated body or a double-encoded one.
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "content-encoding",
    "content-length",
}

PROXY_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class Copy:
    """One dispensed container, and how to reach it from this process."""
    container_id: str
    port: int
    kind: str = ""
    image: str = ""
    # A stable alias for "the copy of this image", when the packager assigned
    # one. A generated site needs it: its bundle is compiled with a fixed
    # basePath, so the path it is served under has to be decided before the
    # container exists. Container ids stay the primary key — they are the
    # honest name for a disposable thing, and two copies of one image must
    # remain separately addressable and separately returnable.
    key: str = ""

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def public_key(self) -> str:
        """What a viewer's URL should carry: the stable key when there is one."""
        return self.key or self.container_id


class Registry:
    """The copies this front door knows how to reach.

    Deliberately in-memory: a dispensed copy is disposable and does not
    survive a restart either, so persisting the routing table would only
    create entries pointing at containers that are gone.
    """

    def __init__(self) -> None:
        self._copies: dict[str, Copy] = {}

    def add(self, copy: Copy) -> Copy:
        self._copies[copy.container_id] = copy
        # The stable key resolves to the most recent copy of that image. Two
        # copies of one site would share it, and the newer one wins — which is
        # the right answer for a prefix baked into a bundle: both bundles ask
        # for the same path, so only one of them can own it. Addressing a
        # specific copy is still exact, by container id.
        if copy.key:
            self._copies[copy.key] = copy
        return copy

    def get(self, container_id: str) -> Copy | None:
        return self._copies.get(container_id)

    def drop(self, container_id: str) -> None:
        copy = self._copies.pop(container_id, None)
        # Only clear the alias if it still points at the copy being dropped;
        # a newer copy may already have claimed it.
        if copy and copy.key and self._copies.get(copy.key) is copy:
            self._copies.pop(copy.key, None)

    def all(self) -> list[Copy]:
        return list(self._copies.values())


def public_path(container_id: str) -> str:
    """Where a viewer reaches this copy — a path, not an origin.

    A path means the answer is correct on a laptop, on the hosted face, and
    behind whatever hostname either is using, without this code ever having
    to learn what that hostname is.
    """
    return f"/dispensed/{container_id}/"


def _rebase_html(body: bytes, base: str) -> bytes:
    """Give an HTML document a <base> so its relative links resolve.

    Injected after <head> when there is one, and prepended otherwise. This is
    what makes an ordinary generated page work under a prefix; it does
    nothing for absolute paths, which is stated in the module docstring
    rather than pretended away here.
    """
    tag = f'<base href="{base}">'.encode()
    lower = body[:4096].lower()
    idx = lower.find(b"<head>")
    if idx != -1:
        cut = idx + len(b"<head>")
        return body[:cut] + tag + body[cut:]
    return tag + body


async def forward(copy: Copy, path: str, request) -> Response:
    """Pass one request through to a dispensed copy and return its answer."""
    url = f"{copy.origin}/{path.lstrip('/')}"
    body = await request.body()
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in HOP_BY_HOP | {"host"}}
    try:
        async with httpx.AsyncClient(follow_redirects=False) as client:
            r = await client.request(
                request.method, url, params=dict(request.query_params),
                content=body or None, headers=headers, timeout=PROXY_TIMEOUT_S)
    except httpx.HTTPError as e:
        # A copy that has been thrown away, or one still starting. Either way
        # the viewer needs to know it is the COPY that is gone, not the face.
        raise HTTPException(
            502, f"the dispensed copy is not answering: {type(e).__name__}") from None

    out = {k: v for k, v in r.headers.items() if k.lower() not in HOP_BY_HOP}
    content = r.content
    ctype = r.headers.get("content-type", "")

    if "text/html" in ctype:
        content = _rebase_html(content, public_path(copy.container_id))
    # A redirect to the copy's own root must stay inside the proxy, or the
    # viewer is bounced to a loopback address that means nothing to them.
    location = r.headers.get("location")
    if location and location.startswith("/"):
        out["location"] = public_path(copy.container_id).rstrip("/") + location

    return Response(content=content, status_code=r.status_code,
                    headers=out, media_type=ctype or None)
