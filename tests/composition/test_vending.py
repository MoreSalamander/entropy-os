"""The vending machine: gated artifacts become images, copies get dispensed.

The claims worth testing are about admission and honesty, not about Docker.
Docker-requiring tests skip when the daemon is absent; the rules they guard —
what is stock, what is refused, and why — are checked without it.
"""

from __future__ import annotations

import urllib.request

import pytest

from entropy_os.composition.contract import ArtifactRef, ExecuteResult
from entropy_os.composition.scaffold import (
    Determinism,
    EvidenceFloor,
    StageJudgment,
    VerificationPassed,
)
from entropy_os.composition.vending import (
    VendingError,
    available,
    image_tag,
    package,
    packageable,
    stop,
    vend,
)

# --------------------------------------------------------------------------- #
# admission — the gate decides what is stock
# --------------------------------------------------------------------------- #

def _blocked() -> StageJudgment:
    verdict = EvidenceFloor().evaluate(
        ExecuteResult(status="completed", outputs={"entities": 0, "claims": 0}))
    return StageJudgment(stage_seq=1, engine="research", verdicts=[verdict])


def _held() -> StageJudgment:
    verdict = VerificationPassed().evaluate(
        ExecuteResult(status="completed",
                      outputs={"verification_passed": False}))
    return StageJudgment(stage_seq=3, engine="software", verdicts=[verdict])


def _passed() -> StageJudgment:
    verdict = EvidenceFloor().evaluate(
        ExecuteResult(status="completed",
                      outputs={"entities": 9, "claims": 20}))
    return StageJudgment(stage_seq=1, engine="research", verdicts=[verdict])


def test_a_blocked_stage_produces_no_stock(tmp_path):
    """The machine does not form its own opinion about quality — it reads the
    verdict the scaffold already reached."""
    report = tmp_path / "r.md"
    report.write_text("# findings")
    art = ArtifactRef(kind="report", path=str(report))

    with pytest.raises(VendingError) as e:
        package(art, "obj-x", judgment=_blocked())
    assert "not stock" in str(e.value)
    assert "evidence_floor" in str(e.value)


def test_a_held_stage_produces_no_stock_either(tmp_path):
    """Held is not "maybe ship it": until a human decides, it is not stock."""
    report = tmp_path / "r.md"
    report.write_text("# findings")
    with pytest.raises(VendingError) as e:
        package(ArtifactRef(kind="report", path=str(report)), "obj-x",
                judgment=_held())
    assert "not stock" in str(e.value)
    assert "verification_passed" in str(e.value)
    assert _held().verdicts[0].determinism is Determinism.HUMAN


def test_the_gate_is_checked_before_the_infrastructure(tmp_path):
    """A rejected artifact must be reported as rejected, not as a Docker
    problem — otherwise a quality failure reads as an ops failure."""
    missing = ArtifactRef(kind="report", path=str(tmp_path / "nope.md"))
    with pytest.raises(VendingError) as e:
        package(missing, "obj-x", judgment=_blocked())
    assert "not stock" in str(e.value)      # gate, not the missing path


# --------------------------------------------------------------------------- #
# honest refusal — what this machine cannot package, it says so
# --------------------------------------------------------------------------- #

def test_a_next_js_site_is_refused_with_the_real_reason(tmp_path):
    """design-engine emits source, not a served bundle. Shipping an unbuilt
    tree as though it were a running site would be a lie, so it is refused
    with the reason rather than packaged badly."""
    site = tmp_path / "site"
    site.mkdir()
    (site / "package.json").write_text("{}")
    ok, why = packageable(ArtifactRef(kind="site", path=str(site)))
    assert ok is False
    assert "node build" in why


def test_a_sidecar_is_not_a_product(tmp_path):
    ok, why = packageable(ArtifactRef(kind="sidecar", path=str(tmp_path)))
    assert ok is False and "not a product" in why


def test_an_unknown_kind_is_refused_rather_than_guessed(tmp_path):
    ok, why = packageable(ArtifactRef(kind="hologram", path=str(tmp_path)))
    assert ok is False and "no packaging strategy" in why


def test_a_project_without_its_dockerfile_names_the_real_problem(tmp_path):
    """code-engine generates a Dockerfile; its absence is the defect, and the
    message should say that rather than blaming packaging."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "app").mkdir()
    docker_ok, _ = available()
    if not docker_ok:
        pytest.skip("docker unavailable")
    with pytest.raises(VendingError) as e:
        package(ArtifactRef(kind="project", path=str(proj)), "obj-x")
    assert "no Dockerfile" in str(e.value)


def test_tags_are_readable_and_scoped_to_the_objective():
    tag = image_tag("obj-abc123", "report", "session_9f.md")
    assert tag == "one-engine/report-session-9f-md:obj-abc123"


# --------------------------------------------------------------------------- #
# the real thing — build once, dispense many
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(not available()[0], reason="docker unavailable")
def test_a_gated_document_becomes_a_servable_container(tmp_path):
    report = tmp_path / "session_test.md"
    report.write_text("# Findings\n\nWebGPU compute shaders dispatch in "
                      "workgroups.\n")
    art = ArtifactRef(kind="report", path=str(report),
                      description="research report: test")

    item = package(art, "obj-vendtest", judgment=_passed())
    assert item.image.startswith("one-engine/report-")
    assert item.kind == "report"

    copy = vend(item)
    try:
        with urllib.request.urlopen(copy.url, timeout=10) as r:
            body = r.read().decode()
        assert r.status == 200
        # The content is really in there, and so is its provenance.
        assert "workgroups" in body
        assert "obj-vendtest" in body
        assert copy.url.startswith("http://127.0.0.1:")   # loopback only
    finally:
        stop(copy.container_id)


@pytest.mark.skipif(not available()[0], reason="docker unavailable")
def test_dispensing_twice_hands_out_two_different_containers(tmp_path):
    """Build once, dispense many: the image is reused, the instance never is.
    A copy you are handed, not a shared box everyone reaches."""
    report = tmp_path / "r.md"
    report.write_text("# once\n")
    item = package(ArtifactRef(kind="report", path=str(report)), "obj-twice")

    a = vend(item)
    b = vend(item)
    try:
        assert a.image == b.image
        assert a.container_id != b.container_id
        assert a.port != b.port
    finally:
        stop(a.container_id)
        stop(b.container_id)


@pytest.mark.skipif(not available()[0], reason="docker unavailable")
def test_rebuilding_the_same_artifact_replaces_its_stock(tmp_path):
    """Idempotent by tag, so re-running an objective replaces the stock rather
    than littering the image list."""
    report = tmp_path / "r.md"
    report.write_text("# v1\n")
    first = package(ArtifactRef(kind="report", path=str(report)), "obj-same")
    report.write_text("# v2\n")
    second = package(ArtifactRef(kind="report", path=str(report)), "obj-same")
    assert first.image == second.image

    copy = vend(second)
    try:
        with urllib.request.urlopen(copy.url, timeout=10) as r:
            assert "v2" in r.read().decode()
    finally:
        stop(copy.container_id)
