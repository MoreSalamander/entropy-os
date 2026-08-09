"""Docker plumbing for dispensing artifacts as containers.

Converges deliberately with Veritas's vending machine
(`products/tutorial/container.py`): **build once, dispense many.** An image is
built per artifact when its gates pass; a fresh disposable container is run
every time someone asks for a copy. The image is reused, the instance never is
— you are handed a copy, not pointed at a shared box.

Two details are carried over because Veritas paid for them:

  * `shutil.which("docker")` returns None under a LaunchAgent even where
    docker works fine in a terminal, so explicit path fallbacks are checked.
  * Readiness must be an HTTP GET, not a TCP connect. The kernel accepts a
    connection into the listen backlog before the server can answer it, so a
    bare connect succeeds and the first real request gets reset.

Not imported from Veritas on purpose: one-engine is a composable system in its
own right and must not depend on another. Same discipline, own copy.
"""

from __future__ import annotations

import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

_DOCKER_FALLBACKS = ("/opt/homebrew/bin/docker", "/usr/local/bin/docker",
                     "/Applications/Docker.app/Contents/Resources/bin/docker")


def _find_docker() -> str:
    found = shutil.which("docker")
    if found:
        return found
    for candidate in _DOCKER_FALLBACKS:
        if Path(candidate).exists():
            return candidate
    return "docker"      # let the eventual call fail loudly rather than guess


DOCKER = _find_docker()


class VendingError(Exception):
    """Packaging or dispensing failed. The message carries the evidence, so a
    caller can report why rather than shipping anyway."""


def available() -> tuple[bool, str]:
    """Whether a container can be built or run at all.

    Refusing honestly matters here: an artifact that cannot be isolated must
    not be handed over unisolated instead.
    """
    try:
        proc = subprocess.run([DOCKER, "info"], capture_output=True,
                              timeout=20)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"docker not runnable ({type(e).__name__}: {e})"
    if proc.returncode != 0:
        return False, "docker is installed but the daemon is not responding"
    return True, f"docker ready at {DOCKER}"


@dataclass(frozen=True)
class DispensedCopy:
    """One disposable container, handed out."""
    container_id: str
    image: str
    url: str
    port: int


def build(context: Path, tag: str, dockerfile: str | None = None,
          timeout_s: int = 900) -> str:
    """`docker build` the context into `tag`.

    Idempotent by tag: rebuilding the same artifact overwrites the same tag
    rather than littering the image list, so re-running a run replaces its
    stock instead of accumulating it.
    """
    cmd = [DOCKER, "build", "-t", tag]
    if dockerfile:
        cmd += ["-f", dockerfile]
    cmd.append(str(context))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout_s)
    except subprocess.TimeoutExpired as e:
        raise VendingError(
            f"docker build timed out after {timeout_s}s for {tag}") from e
    if proc.returncode != 0:
        raise VendingError(f"docker build failed for {tag}: "
                           f"{proc.stderr[-1200:]}")
    return tag


def dispense(image: str, container_port: int = 80,
             ready_path: str = "/") -> DispensedCopy:
    """`docker run` a fresh disposable copy, on a Docker-assigned loopback port.

    `--rm` means stopping it removes it. Bound to 127.0.0.1 only: a dispensed
    copy is for whoever asked, not published to the network.
    """
    proc = subprocess.run(
        [DOCKER, "run", "--rm", "-d", "-p", f"127.0.0.1::{container_port}",
         image],
        capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise VendingError(f"docker run failed for {image}: "
                           f"{proc.stderr[-800:]}")
    container_id = proc.stdout.strip()

    port_proc = subprocess.run(
        [DOCKER, "port", container_id, f"{container_port}/tcp"],
        capture_output=True, text=True, timeout=15)
    if port_proc.returncode != 0 or not port_proc.stdout.strip():
        stop(container_id)
        raise VendingError(f"could not read the assigned port for "
                           f"{container_id}: {port_proc.stderr}")
    host_port = int(port_proc.stdout.strip().rsplit(":", 1)[-1])

    _wait_until_serving(host_port, ready_path)
    return DispensedCopy(container_id=container_id, image=image,
                         url=f"http://127.0.0.1:{host_port}", port=host_port)


def stop(container_id: str) -> None:
    subprocess.run([DOCKER, "stop", "-t", "1", container_id],
                   capture_output=True, timeout=20)


def _wait_until_serving(port: int, path: str, timeout: float = 20.0) -> None:
    """Wait for an actual HTTP answer.

    `docker run -d` returns when the process starts, not when the server can
    serve. A TCP connect is not proof — the kernel accepts into the listen
    backlog first, so the connect succeeds and the request that follows gets
    reset. Only a response is evidence. Best effort: if it never comes, the
    caller's own request surfaces the failure honestly.
    """
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}{path}"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return
        except urllib.error.HTTPError as e:
            if e.code < 500:      # a 404 still proves the server is answering
                return
        except (urllib.error.URLError, OSError, TimeoutError):
            pass
        time.sleep(0.25)
