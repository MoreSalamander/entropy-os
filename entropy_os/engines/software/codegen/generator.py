"""Phase 8 — deterministic project generation from the validated Architecture.

The Implementation Agents (backend, database, frontend), Testing Agent, and
Documentation Agent all live here as generation passes. No LLM writes code:
every file derives mechanically from the Architecture, and every write
registers provenance in the Context Graph (component → file, test → feature)
as it happens — the semantic model is a byproduct of generation, not an
afterthought.

Generated repository:
    app/{main,db,models,schemas}.py, app/routers/*, app/services/*
    static/{index.html,app.js}              (when web_ui exists)
    tests/{conftest.py,test_*.py}
    docs/{architecture.md,api.md}           (from the graph, never prose-only)
    requirements.txt, requirements-dev.txt, Dockerfile, README.md
    .entropy_os.engines.software/graph.json                 (sidecar, written by the engine)

Custom (non-CRUD) endpoints generate honest visible stubs — they return
{"implemented": false, ...}, carry a test asserting reachability, and are
recorded in the graph as known problems so nothing pretends to exist.
"""

from __future__ import annotations

from pathlib import Path

from ..graphs.context_graph import SoftwareContextGraph
from ..models import (ApiEndpoint, Architecture, Component, EntityModel,
                      GeneratedProject, SoftwareSpec)

_SQLA_TYPES = {"str": "String(255)", "text": "Text", "int": "Integer",
               "float": "Float", "bool": "Boolean", "datetime": "DateTime"}
_PY_TYPES = {"str": "str", "text": "str", "int": "int", "float": "float",
             "bool": "bool", "datetime": "datetime"}

PATTERNS_APPLIED = ["router_service_split", "session_per_request",
                    "schema_in_schema_out", "tests_per_feature",
                    "sidecar_self_model"]


class ProjectGenerator:
    def __init__(self, out_dir: Path):
        self.out = out_dir

    # ------------------------------------------------------------------ #
    def generate(self, spec: SoftwareSpec, arch: Architecture,
                 cg: SoftwareContextGraph) -> GeneratedProject:
        self.out.mkdir(parents=True, exist_ok=True)
        files = 0
        files += self._scaffolding(spec, arch, cg)
        files += self._database_layer(arch, cg)
        files += self._schemas(arch, cg)
        for comp in arch.components:
            if comp.kind == "service":
                files += self._service_and_router(comp, arch, cg)
        files += self._main_app(spec, arch, cg)
        if any(c.name == "web_ui" for c in arch.components):
            files += self._frontend(spec, arch, cg)
        files += self._tests(arch, cg)
        files += self._docs(spec, arch, cg)
        self._ruff_fix_pass()
        return GeneratedProject(project_id=cg.project_id, spec=spec,
                                architecture=arch, out_dir=str(self.out),
                                files_written=files)

    def _ruff_fix_pass(self) -> None:
        """Generation ends with `ruff check --fix` over the emitted tree —
        the same idea as gofmt: safe mechanical fixes (import order, unused
        imports) are part of generation, so verification's ruff gate judges
        substance, not formatting debt."""
        import subprocess
        import sys
        subprocess.run([sys.executable, "-m", "ruff", "check", "--fix", "-q",
                        "app", "tests"],
                       cwd=self.out, capture_output=True, timeout=60,
                       check=False)

    def _write(self, rel: str, content: str, cg: SoftwareContextGraph,
               component: str, role: str) -> int:
        path = self.out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        cg.add_file(rel, component, role)
        return 1

    # ------------------------------------------------------------------ #
    # scaffolding (DevOps slice of the Implementation Agents)
    # ------------------------------------------------------------------ #
    def _scaffolding(self, spec: SoftwareSpec, arch: Architecture,
                     cg: SoftwareContextGraph) -> int:
        n = 0
        n += self._write("requirements.txt",
                         "fastapi>=0.115\nuvicorn>=0.32\nSQLAlchemy>=2.0\n"
                         "pydantic>=2.10\n", cg, "database", "config")
        n += self._write("requirements-dev.txt",
                         "-r requirements.txt\npytest>=8.3\nhttpx>=0.27\n"
                         "ruff>=0.8\n", cg, "database", "config")
        n += self._write("Dockerfile", (
            "FROM python:3.12-slim\n"
            "WORKDIR /srv\n"
            "COPY requirements.txt .\n"
            "RUN pip install --no-cache-dir -r requirements.txt\n"
            "COPY . .\n"
            "EXPOSE 8000\n"
            'CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]\n'),
            cg, "database", "infra")
        n += self._write(".gitignore", "__pycache__/\n*.pyc\n*.db\n.venv/\n",
                         cg, "database", "config")
        # hermetic lint config: the verification gate's ruleset ships WITH the
        # project, so results never depend on global/parent ruff configs
        n += self._write("ruff.toml", (
            'line-length = 100\n\n'
            '[lint]\n'
            'select = ["E4", "E7", "E9", "F", "I", "B"]\n\n'
            '[lint.flake8-bugbear]\n'
            'extend-immutable-calls = ["fastapi.Depends"]\n'),
            cg, "database", "config")
        n += self._write("app/__init__.py", "", cg, "database", "package")
        return n

    # ------------------------------------------------------------------ #
    # database layer (Database Implementation Agent)
    # ------------------------------------------------------------------ #
    def _database_layer(self, arch: Architecture, cg: SoftwareContextGraph) -> int:
        db_py = '''"""Database wiring: SQLite via SQLAlchemy, session per request."""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data.db")

engine = create_engine(DATABASE_URL,
                       connect_args={"check_same_thread": False}
                       if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_session():
    """FastAPI dependency: one session per request, always closed."""
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    from app import models  # noqa: F401 — models must import before create_all
    Base.metadata.create_all(engine)
'''
        n = self._write("app/db.py", db_py, cg, "database", "source")

        lines = ['"""SQLAlchemy models — one class per domain entity."""', "",
                 "from datetime import datetime  # noqa: F401", "",
                 "from sqlalchemy import (Boolean, DateTime, Float, Integer,  # noqa: F401",
                 "                        String, Text)",
                 "from sqlalchemy.orm import Mapped, mapped_column", "",
                 "from app.db import Base", ""]
        for ent in arch.entities:
            lines += ["", f"class {ent.name}(Base):",
                      f'    __tablename__ = "{ent.snake}s"', "",
                      "    id: Mapped[int] = mapped_column(Integer, primary_key=True)"]
            for f in ent.fields:
                py = _PY_TYPES[f.type]
                sqla = _SQLA_TYPES[f.type]
                nullable = "" if f.required else ", nullable=True"
                opt = "" if f.required else " | None"
                lines.append(f"    {f.name}: Mapped[{py}{opt}] = "
                             f"mapped_column({sqla}{nullable})")
        n += self._write("app/models.py", "\n".join(lines) + "\n",
                         cg, "database", "source")
        return n

    # ------------------------------------------------------------------ #
    def _schemas(self, arch: Architecture, cg: SoftwareContextGraph) -> int:
        lines = ['"""Pydantic schemas: every request validated, every response shaped."""',
                 "", "from datetime import datetime  # noqa: F401", "",
                 "from pydantic import BaseModel, ConfigDict", ""]
        for ent in arch.entities:
            lines += ["", f"class {ent.name}Create(BaseModel):"]
            for f in ent.fields:
                py = _PY_TYPES[f.type]
                default = "" if f.required else " | None = None"
                lines.append(f"    {f.name}: {py}{default}")
            lines += ["", "", f"class {ent.name}Read({ent.name}Create):",
                      "    model_config = ConfigDict(from_attributes=True)", "",
                      "    id: int"]
        return self._write("app/schemas.py", "\n".join(lines) + "\n",
                           cg, "database", "source")

    # ------------------------------------------------------------------ #
    # per-component service + router (Backend Implementation Agent)
    # ------------------------------------------------------------------ #
    def _service_and_router(self, comp: Component, arch: Architecture,
                            cg: SoftwareContextGraph) -> int:
        ents = {e.name: e for e in arch.entities}
        n = 0

        # ---- service module: logic layer, no HTTP concerns ------------
        svc = [f'"""Service layer for {comp.name}: {comp.purpose}"""', "",
               "from sqlalchemy import select",
               "from sqlalchemy.orm import Session", ""]
        if comp.entities:
            svc.append("from app import models")
        for en in comp.entities:
            ent = ents[en]
            svc += ["", "",
                    f"def list_{ent.snake}s(session: Session) -> list[models.{en}]:",
                    f"    return list(session.scalars(select(models.{en})).all())",
                    "", "",
                    f"def get_{ent.snake}(session: Session, item_id: int) -> models.{en} | None:",
                    f"    return session.get(models.{en}, item_id)",
                    "", "",
                    f"def create_{ent.snake}(session: Session, data: dict) -> models.{en}:",
                    f"    obj = models.{en}(**data)",
                    "    session.add(obj)",
                    "    session.commit()",
                    "    session.refresh(obj)",
                    "    return obj",
                    "", "",
                    f"def delete_{ent.snake}(session: Session, item_id: int) -> bool:",
                    f"    obj = session.get(models.{en}, item_id)",
                    "    if obj is None:",
                    "        return False",
                    "    session.delete(obj)",
                    "    session.commit()",
                    "    return True"]
        n += self._write(f"app/services/{comp.name}.py", "\n".join(svc) + "\n",
                         cg, comp.name, "source")

        # ---- router: thin HTTP layer over the service ------------------
        # imports are conditional on what the endpoints actually use — a
        # stub-only router must not carry dead imports (live-run F401s)
        crud_eps = [ep for ep in comp.endpoints if ep.action != "custom"]
        needs_404 = any(ep.action in ("get", "delete", "update") for ep in crud_eps)
        fastapi_names = ["APIRouter"] + (["Depends"] if crud_eps else []) \
            + (["HTTPException"] if needs_404 else [])
        rt = [f'"""Router for {comp.name}. Thin by design: logic lives in the service."""',
              "",
              f"from fastapi import {', '.join(fastapi_names)}"]
        if crud_eps:
            rt[1:1] = ["", "from typing import Annotated"]
            rt += ["from sqlalchemy.orm import Session", "",
                   "from app import schemas",
                   "from app.db import get_session",
                   f"from app.services import {comp.name} as service"]
        rt += ["", f'router = APIRouter(tags=["{comp.name}"])']
        for ep in comp.endpoints:
            ent = ents.get(ep.entity)
            fn = f"{ep.action}_{ent.snake if ent else 'op'}_{abs(hash(ep.method + ep.path)) % 1000}"
            if ep.action == "list" and ent:
                rt += ["", "",
                       f'@router.get("{ep.path}", response_model=list[schemas.{ent.name}Read])',
                       f"def {fn}(session: Annotated[Session, Depends(get_session)]):",
                       f'    """{ep.summary}"""',
                       f"    return service.list_{ent.snake}s(session)"]
            elif ep.action == "get" and ent:
                rt += ["", "",
                       f'@router.get("{ep.path}", response_model=schemas.{ent.name}Read)',
                       f"def {fn}(item_id: int, session: Annotated[Session, Depends(get_session)]):",
                       f'    """{ep.summary}"""',
                       f"    obj = service.get_{ent.snake}(session, item_id)",
                       "    if obj is None:",
                       f'        raise HTTPException(404, "{ent.name} not found")',
                       "    return obj"]
            elif ep.action == "create" and ent:
                rt += ["", "",
                       f'@router.post("{ep.path}", response_model=schemas.{ent.name}Read, status_code=201)',
                       f"def {fn}(payload: schemas.{ent.name}Create, "
                       "session: Annotated[Session, Depends(get_session)]):",
                       f'    """{ep.summary}"""',
                       f"    return service.create_{ent.snake}(session, payload.model_dump())"]
            elif ep.action == "delete" and ent:
                rt += ["", "",
                       f'@router.delete("{ep.path}", status_code=204)',
                       f"def {fn}(item_id: int, session: Annotated[Session, Depends(get_session)]):",
                       f'    """{ep.summary}"""',
                       f"    if not service.delete_{ent.snake}(session, item_id):",
                       f'        raise HTTPException(404, "{ent.name} not found")']
            elif ep.action == "update" and ent:
                rt += ["", "",
                       f'@router.put("{ep.path}", response_model=schemas.{ent.name}Read)',
                       f"def {fn}(item_id: int, payload: schemas.{ent.name}Create, "
                       "session: Annotated[Session, Depends(get_session)]):",
                       f'    """{ep.summary}"""',
                       f"    obj = service.get_{ent.snake}(session, item_id)",
                       "    if obj is None:",
                       f'        raise HTTPException(404, "{ent.name} not found")',
                       "    for key, value in payload.model_dump().items():",
                       "        setattr(obj, key, value)",
                       "    session.commit()",
                       "    session.refresh(obj)",
                       "    return obj"]
            else:
                # honest visible stub — recorded as a known problem
                method = ep.method.lower()
                rt += ["", "",
                       f'@router.{method}("{ep.path}")',
                       f"def {fn}():",
                       f'    """{ep.summary} (STUB — custom logic not yet implemented)"""',
                       '    return {"implemented": False,',
                       f'            "endpoint": "{ep.method} {ep.path}",',
                       f'            "summary": "{ep.summary}"}}'.replace("}}", "}")]
                cg.add_problem(f"custom endpoint stub: {ep.method} {ep.path}",
                               f"api:{ep.method} {ep.path}", source="codegen")
        n += self._write(f"app/routers/{comp.name}.py", "\n".join(rt) + "\n",
                         cg, comp.name, "source")
        return n

    # ------------------------------------------------------------------ #
    def _main_app(self, spec: SoftwareSpec, arch: Architecture,
                  cg: SoftwareContextGraph) -> int:
        service_comps = [c for c in arch.components
                         if c.kind == "service" and c.endpoints]
        has_ui = any(c.name == "web_ui" for c in arch.components)
        lines = [f'"""{spec.product_name} — generated by code-engine.', "",
                 f"{spec.purpose}", '"""', "",
                 "from fastapi import FastAPI"]
        if has_ui:
            lines.append("from fastapi.staticfiles import StaticFiles")
        lines += ["", "from app.db import init_db"]
        for comp in service_comps:
            lines.append(f"from app.routers import {comp.name}")
        lines += ["",
                  f'app = FastAPI(title="{spec.product_name}",',
                  f'              description="{spec.purpose[:150]}")', "",
                  "init_db()", ""]
        for comp in service_comps:
            lines.append(f"app.include_router({comp.name}.router)")
        lines += ["", "",
                  '@app.get("/health")',
                  "def health() -> dict:",
                  '    return {"status": "ok"}']
        if has_ui:
            lines += ["", "",
                      'app.mount("/", StaticFiles(directory="static", html=True), '
                      'name="ui")']
        n = self._write("app/main.py", "\n".join(lines) + "\n",
                        cg, service_comps[0].name if service_comps else "database",
                        "source")
        n += self._write("app/routers/__init__.py", "", cg, "database", "package")
        n += self._write("app/services/__init__.py", "", cg, "database", "package")
        return n

    # ------------------------------------------------------------------ #
    def _frontend(self, spec: SoftwareSpec, arch: Architecture,
                  cg: SoftwareContextGraph) -> int:
        first_list = None
        for comp in arch.components:
            for ep in comp.endpoints:
                if ep.action == "list":
                    first_list = ep
                    break
            if first_list:
                break
        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{spec.product_name}</title>
<style>
  body {{ font: 16px/1.6 system-ui, sans-serif; max-width: 720px;
         margin: 3rem auto; padding: 0 1rem; color: #1c2733; }}
  h1 {{ letter-spacing: -0.02em; }}
  #items li {{ padding: .4rem 0; border-bottom: 1px solid #e5e9ef; }}
  .muted {{ color: #6b7a8c; }}
</style>
</head>
<body>
<h1>{spec.product_name}</h1>
<p class="muted">{spec.purpose}</p>
<ul id="items"><li class="muted">Loading…</li></ul>
<script src="/app.js"></script>
</body>
</html>
'''
        list_path = first_list.path if first_list else "/health"
        js = f'''// Minimal dependency-free frontend over the generated API.
async function load() {{
  const target = document.getElementById("items");
  try {{
    const res = await fetch("{list_path}");
    const data = await res.json();
    const rows = Array.isArray(data) ? data : [data];
    target.innerHTML = rows.length
      ? rows.map((r) => `<li>${{JSON.stringify(r)}}</li>`).join("")
      : '<li class="muted">No records yet.</li>';
  }} catch (err) {{
    target.innerHTML = `<li class="muted">API unavailable: ${{err}}</li>`;
  }}
}}
load();
'''
        n = self._write("static/index.html", html, cg, "web_ui", "source")
        n += self._write("static/app.js", js, cg, "web_ui", "source")
        return n

    # ------------------------------------------------------------------ #
    # Testing Agent: tests per feature, provenance recorded
    # ------------------------------------------------------------------ #
    def _tests(self, arch: Architecture, cg: SoftwareContextGraph) -> int:
        conftest = '''"""Test wiring: isolated temp database + TestClient per session."""

import os
import tempfile

os.environ["DATABASE_URL"] = (
    "sqlite:///" + tempfile.mkstemp(suffix=".db")[1])

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
'''
        n = self._write("tests/conftest.py", conftest, cg, "database", "test")

        ents = {e.name: e for e in arch.entities}
        sample_values = {"str": '"sample text"', "text": '"longer sample body"',
                         "int": "3", "float": "1.5", "bool": "True",
                         "datetime": '"2026-01-01T00:00:00"'}
        for comp in arch.components:
            if comp.kind != "service" or not comp.endpoints:
                continue
            feature_id = comp.feature_ids[0] if comp.feature_ids else ""
            lines = [f'"""Generated tests for component {comp.name}."""', ""]
            test_names: list[str] = []
            done_entities: set[str] = set()
            for ep in comp.endpoints:
                ent = ents.get(ep.entity)
                if ent and ent.name not in done_entities and ep.action in (
                        "list", "create"):
                    done_entities.add(ent.name)
                    payload = ", ".join(f'"{f.name}": {sample_values[f.type]}'
                                        for f in ent.fields)
                    base = next((e.path for e in comp.endpoints
                                 if e.entity == ent.name and e.action == "list"),
                                None)
                    create = next((e.path for e in comp.endpoints
                                   if e.entity == ent.name and e.action == "create"),
                                  None)
                    if base and create:
                        name = f"test_{ent.snake}_create_and_list"
                        test_names.append(name)
                        lines += [
                            "",
                            f"def {name}(client):",
                            f"    created = client.post(\"{create}\", json={{{payload}}})",
                            "    assert created.status_code == 201, created.text",
                            '    assert created.json()["id"] >= 1',
                            f"    listed = client.get(\"{base}\")",
                            "    assert listed.status_code == 200",
                            "    assert any(row[\"id\"] == created.json()[\"id\"]"
                            " for row in listed.json())"]
                    get_ep = next((e.path for e in comp.endpoints
                                   if e.entity == ent.name and e.action == "get"),
                                  None)
                    if get_ep:
                        name = f"test_{ent.snake}_missing_returns_404"
                        test_names.append(name)
                        lines += [
                            "", "",
                            f"def {name}(client):",
                            f"    res = client.get(\"{get_ep.replace('{item_id}', '999999')}\")",
                            "    assert res.status_code == 404"]
                if ep.action == "custom":
                    name = f"test_custom_{abs(hash(ep.method + ep.path)) % 1000}_reachable"
                    test_names.append(name)
                    method = ep.method.lower()
                    lines += [
                        "", "",
                        f"def {name}(client):",
                        f"    res = client.{method}(\"{ep.path}\")",
                        "    assert res.status_code == 200",
                        '    assert res.json()["implemented"] is False']
            if not test_names:
                continue
            rel = f"tests/test_{comp.name}.py"
            n += self._write(rel, "\n".join(lines) + "\n", cg, comp.name, "test")
            for tname in test_names:
                cg.add_test(rel, tname, feature_id, comp.name)

        smoke = '''"""Smoke: app boots, health answers, schema is reachable."""


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_openapi_lists_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/health" in paths
'''
        n += self._write("tests/test_smoke.py", smoke, cg, "database", "test")
        return n

    # ------------------------------------------------------------------ #
    # Documentation Agent: docs FROM the model, never freehand
    # ------------------------------------------------------------------ #
    def _docs(self, spec: SoftwareSpec, arch: Architecture,
              cg: SoftwareContextGraph) -> int:
        comp_names = [c.name for c in arch.components]
        md = [f"# {spec.product_name} — Architecture", "",
              f"_{spec.purpose}_", "",
              "Generated by code-engine; this document derives from the "
              "system model in `.entropy_os.engines.software/graph.json`.", "",
              "## Components", "",
              "| Component | Kind | Purpose | Depends on |", "|---|---|---|---|"]
        for c in arch.components:
            md.append(f"| {c.name} | {c.kind} | {c.purpose[:80]} | "
                      f"{', '.join(c.depends_on) or '—'} |")
        md += ["", "## Entities", ""]
        for e in arch.entities:
            md.append(f"- **{e.name}**: " +
                      ", ".join(f"{f.name}:{f.type}" for f in e.fields))
        md += ["", "## Decisions", ""]
        for d in arch.decisions:
            md += [f"### {d.title}", "", d.decision, "",
                   f"_Rationale:_ {d.rationale}", ""]
        md += ["## Features → Requirements", ""]
        for f in arch.features:
            md.append(f"- **{f.name}** — {f.description[:100]} "
                      f"(satisfies {len(f.requirement_ids)} requirement(s))")
        n = self._write("docs/architecture.md", "\n".join(md) + "\n",
                        cg, arch.components[0].name, "doc")
        cg.add_doc("docs/architecture.md", comp_names)

        api_md = [f"# {spec.product_name} — API", ""]
        for c in arch.components:
            if not c.endpoints:
                continue
            api_md += [f"## {c.name}", ""]
            for ep in c.endpoints:
                api_md.append(f"- `{ep.method} {ep.path}` — {ep.summary}"
                              + (f" _(entity: {ep.entity})_" if ep.entity else ""))
            api_md.append("")
        n += self._write("docs/api.md", "\n".join(api_md) + "\n",
                         cg, arch.components[0].name, "doc")
        cg.add_doc("docs/api.md", [c.name for c in arch.components if c.endpoints])

        readme = [f"# {spec.product_name}", "", spec.purpose, "",
                  "Generated by [code-engine](https://github.com/MoreSalamander/code-engine). "
                  "The repository carries its own semantic model in "
                  "`.entropy_os.engines.software/graph.json` — impact analysis and evolution "
                  "checks read it.", "",
                  "## Run", "",
                  "```bash", "pip install -r requirements.txt",
                  "uvicorn app.main:app --reload", "```", "",
                  "## Test", "",
                  "```bash", "pip install -r requirements-dev.txt", "pytest", "```", "",
                  "## Honest notes", "",
                  "- Custom endpoints marked `implemented: false` are visible "
                  "stubs awaiting real logic.",
                  "- See `docs/architecture.md` for components and decisions."]
        n += self._write("README.md", "\n".join(readme) + "\n",
                         cg, arch.components[0].name, "doc")
        return n
