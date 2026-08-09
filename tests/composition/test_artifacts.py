"""Finding what a run produced — and being honest about how we found it.

Two things are worth guarding here. First, the distinction between a path the
run recorded and a path derived from an id it recorded: a derived path is a
good guess, not a fact, and anything acting on it deserves to know which it
holds. Second, containment — a route that serves files by a caller-supplied
path is an arbitrary-file read the moment the containment check is wrong.
"""

from __future__ import annotations

from entropy_os.composition.artifacts import resolve


def _stage(seq, engine, produced=None, artifacts=None):
    return {"seq": seq, "engine": engine, "status": "completed",
            "produced": produced or {}, "artifacts": artifacts or []}


# --------------------------------------------------------------------------- #
# recorded beats derived, and the difference is always stated
# --------------------------------------------------------------------------- #

def test_a_recorded_path_is_taken_at_its_word(tmp_path):
    report = tmp_path / "r.md"
    report.write_text("# findings")
    arts = resolve([_stage(1, "research", artifacts=[
        {"kind": "report", "path": str(report), "description": "the report"}])],
        roots={})
    assert len(arts) == 1
    assert arts[0].origin == "recorded"
    assert arts[0].exists is True
    assert arts[0].size_bytes == len("# findings")


def test_a_derived_path_says_it_was_derived(tmp_path):
    """The earliest runs recorded ids but not paths. Resolving those is useful;
    presenting the result as though the run had recorded it is not."""
    reports = tmp_path / "reports"
    reports.mkdir(parents=True)
    (reports / "session_abc.md").write_text("x" * 50)
    arts = resolve([_stage(1, "research", produced={"session_id": "session_abc"})],
                   roots={"research": str(tmp_path)})
    assert arts[0].origin == "convention"
    assert arts[0].exists is True
    assert "not recorded" in arts[0].description


def test_recorded_artifacts_suppress_the_guess(tmp_path):
    """A stage that recorded its paths must not also be guessed at — that would
    produce two entries for one output, one of them speculative."""
    real = tmp_path / "real.md"
    real.write_text("real")
    arts = resolve([_stage(1, "research", produced={"session_id": "session_abc"},
                           artifacts=[{"kind": "report", "path": str(real),
                                       "description": "d"}])],
                   roots={"research": str(tmp_path)})
    assert len(arts) == 1
    assert arts[0].origin == "recorded"


def test_a_derived_path_that_does_not_exist_is_reported_missing(tmp_path):
    """A guess that turns out wrong must read as missing, not as an artifact
    that happens to weigh nothing."""
    arts = resolve([_stage(2, "university", produced={"session_id": "study_x"})],
                   roots={"university": str(tmp_path)})
    assert arts[0].exists is False
    assert arts[0].size_bytes == 0


# --------------------------------------------------------------------------- #
# the last resort: runs that recorded neither paths nor ids
# --------------------------------------------------------------------------- #

def test_ids_are_recovered_from_the_engines_own_completion_events(tmp_path):
    """The flagship run recorded neither artifacts nor `produced`, but the
    engines plainly announced what they had made. Without this its outputs are
    unreachable despite existing on disk."""
    projects = tmp_path / "projects" / "proj_1"
    projects.mkdir(parents=True)
    (projects / "main.py").write_text("print('hi')")
    facts = [{"engine": "software", "kind": "SoftwareBuilt",
              "payload": {"project_id": "proj_1", "product_name": "GPUcademy"}}]
    arts = resolve([_stage(3, "software")], roots={"software": str(tmp_path)},
                   facts=facts)
    assert arts[0].origin == "convention"
    assert arts[0].exists is True
    assert arts[0].file_count == 1


def test_no_ids_anywhere_yields_nothing_rather_than_a_bad_path(tmp_path):
    assert resolve([_stage(3, "software")], roots={"software": str(tmp_path)}) == []


def test_directory_artifacts_are_measured_whole(tmp_path):
    root = tmp_path / "sites" / "site_1"
    (root / "app").mkdir(parents=True)
    (root / "index.html").write_text("a" * 10)
    (root / "app" / "page.tsx").write_text("b" * 20)
    arts = resolve([_stage(4, "web", produced={"project_id": "site_1"})],
                   roots={"web": str(tmp_path)})
    assert arts[0].file_count == 2
    assert arts[0].size_bytes == 30


def test_an_unknown_engine_is_skipped_rather_than_guessed(tmp_path):
    assert resolve([_stage(1, "astrology", produced={"session_id": "s"})],
                   roots={"astrology": str(tmp_path)}) == []


# --------------------------------------------------------------------------- #
# containment — the security of the file route is this check
# --------------------------------------------------------------------------- #

def _confined(root, requested):
    """The route's containment rule, exercised directly: resolve, then require
    the result to sit inside the artifact root."""
    from pathlib import Path
    root = Path(root)
    target = root if root.is_file() else (root / requested)
    try:
        resolved = target.resolve(strict=True)
        base = (root.parent if root.is_file() else root).resolve(strict=True)
        resolved.relative_to(base)
    except (OSError, ValueError):
        return None
    return resolved


def test_a_traversal_out_of_the_artifact_is_refused(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("private")
    art = tmp_path / "site"
    art.mkdir()
    (art / "index.html").write_text("ok")

    assert _confined(art, "index.html") is not None
    assert _confined(art, "../secret.txt") is None
    assert _confined(art, "../../etc/passwd") is None


def test_an_absolute_path_cannot_escape_the_artifact(tmp_path):
    art = tmp_path / "site"
    art.mkdir()
    (art / "index.html").write_text("ok")
    # `root / "/etc/passwd"` collapses to /etc/passwd in pathlib — precisely the
    # trap this check exists to close.
    assert _confined(art, "/etc/passwd") is None


def test_a_symlink_pointing_outside_is_refused(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("private")
    art = tmp_path / "proj"
    art.mkdir()
    (art / "escape").symlink_to(secret)
    # strict resolution follows the link, so containment is judged on the real
    # destination rather than the link's own location.
    assert _confined(art, "escape") is None


def test_a_single_file_artifact_serves_only_itself(tmp_path):
    report = tmp_path / "r.md"
    report.write_text("findings")
    (tmp_path / "other.md").write_text("not yours")
    assert _confined(report, "") == report.resolve()
    # The request path is ignored for a file artifact, so it cannot be steered.
    assert _confined(report, "other.md") == report.resolve()
