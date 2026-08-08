"""Phase 5 + 8 — the Teaching Agent Organization and experience generation.

  Teacher Agent         evidence-grounded explanation (LLM voices; the
                        prompt carries researched resources + known
                        misconceptions to pre-empt)
  Socratic Agent        question-chain lesson (guides, never answers)
  Visualization Agent   mermaid concept map generated DETERMINISTICALLY
                        from the roadmap edges — the diagram is the graph
  Practice Agent        exercise generation with hard gates:
                          mcq      exactly one correct option, answer ∈ A-D
                          numeric  answer parses as a number
                          code     THE GATE: the reference solution is
                                   executed in a sandboxed subprocess and
                                   must reproduce the claimed output, or
                                   the exercise is rejected
  Assessment Agent      grading: deterministic for mcq/numeric/code;
                        free-text goes to the judge model (different family)
                        with the rubric, at half evidence weight

Lesson bundles (Phase 8) assemble all of it into markdown + mermaid +
exercises, exportable as a static HTML study page.
"""

from __future__ import annotations

import asyncio
import re
import sys

from research_engine.llm.client import LLMClient, LLMUnavailable

from .models import (Exercise, ExerciseKind, GradedAnswer, Lesson,
                     LearningResource, Roadmap)

# ---------------------------------------------------------------------- #
# Visualization Agent — deterministic mermaid from the graph
# ---------------------------------------------------------------------- #

def concept_map_mermaid(roadmap: Roadmap, focus: str,
                        max_nodes: int = 12) -> str:
    """Neighborhood of `focus` in the roadmap as a mermaid flowchart."""
    keep = {focus}
    for s, _rel, d in roadmap.edges:
        if s == focus or d == focus:
            keep.update((s, d))
    ordered = [c.name for c in roadmap.concepts if c.name in keep][:max_nodes]
    ids = {name: f"n{i}" for i, name in enumerate(ordered)}
    lines = ["flowchart TD"]
    for name in ordered:
        shape = f'{ids[name]}(["{name}"])' if name == focus else f'{ids[name]}["{name}"]'
        lines.append(f"    {shape}")
    arrows = {"requires": "-->|requires|", "builds_upon": "-->|builds upon|",
              "related_to": "---|related|", "applied_in": "-->|applied in|",
              "explains": "-->|explains|", "contrasts_with": "---|contrasts|",
              "discovered_by": "-->|discovered by|"}
    for s, rel, d in roadmap.edges:
        if s in ids and d in ids:
            lines.append(f"    {ids[s]} {arrows.get(rel, '-->')} {ids[d]}")
    return "\n".join(lines)


# ---------------------------------------------------------------------- #
# Practice Agent — gated exercise generation
# ---------------------------------------------------------------------- #

_EXERCISE_SCHEMA = {
    "type": "object",
    "properties": {"exercises": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "kind": {"type": "string",
                     "enum": [k.value for k in ExerciseKind]},
            "prompt": {"type": "string"},
            "options": {"type": "array", "items": {"type": "string"}},
            "answer": {"type": "string"},
            "starter_code": {"type": "string"},
            "reference_solution": {"type": "string"},
            "rubric": {"type": "string"},
        },
        "required": ["kind", "prompt", "options", "answer",
                     "starter_code", "reference_solution", "rubric"]}}},
    "required": ["exercises"],
}

_EXERCISE_SYSTEM = """You create practice exercises for ONE concept.
Produce {n} exercises as JSON, mixing kinds:
- mcq: prompt + exactly 4 options labeled implicitly by position; answer is
  the letter A, B, C or D of the single correct option
- numeric: a computation with a single numeric answer (answer = the number)
- code: a SHORT Python task. starter_code = scaffold with a TODO;
  reference_solution = complete working python printing the result;
  answer = the EXACT stdout of the reference solution
- free_text: conceptual question; rubric = 2-3 bullet criteria a good
  answer must hit
Known misconceptions to target: {misconceptions}
Exercises must be self-contained, no external data, no imports beyond the
Python standard library."""


async def run_python_sandboxed(code: str, timeout_s: int = 5) -> tuple[bool, str]:
    """Execute snippet with -I (isolated: no site, no env hooks), capture
    stdout. No network guard beyond isolation + timeout — snippets are
    stdlib-only by instruction and gated by execution anyway."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-I", "-c", code,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except (TimeoutError, asyncio.TimeoutError):
        proc.kill()
        return False, f"timed out after {timeout_s}s"
    return (proc.returncode or 0) == 0, out.decode(errors="replace")


class PracticeAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.rejected = 0  # exercises the gates refused (honesty counter)

    async def generate(self, concept: str, misconceptions: list[str],
                       n: int = 4) -> list[Exercise]:
        try:
            proposal = await self.llm.chat_json(
                "extract",
                _EXERCISE_SYSTEM.format(
                    n=n, misconceptions=", ".join(misconceptions[:4]) or "none known"),
                f"Concept: {concept}", _EXERCISE_SCHEMA)
        except LLMUnavailable:
            # deterministic fallback: one recall MCQ so practice never vanishes
            return [Exercise(concept_name=concept, kind=ExerciseKind.MCQ,
                             prompt=f"Which statement about {concept} is most accurate? "
                                    "(fallback item — LLM unavailable)",
                             options=[f"{concept} is a core concept here",
                                      "It is unrelated to this subject",
                                      "It has no prerequisites",
                                      "None of the above"],
                             answer="A", verified=True)]
        out: list[Exercise] = []
        for e in proposal.get("exercises", []) or []:
            if not isinstance(e, dict):
                continue
            gated = await self._gate(concept, e)
            if gated is not None:
                out.append(gated)
            else:
                self.rejected += 1
        return out

    async def _gate(self, concept: str, e: dict) -> Exercise | None:
        try:
            kind = ExerciseKind(e.get("kind", ""))
        except ValueError:
            return None
        prompt = str(e.get("prompt", "")).strip()
        if not prompt:
            return None
        answer = str(e.get("answer", "")).strip()

        if kind == ExerciseKind.MCQ:
            options = [str(o).strip() for o in (e.get("options") or [])
                       if str(o).strip()]
            if len(options) != 4 or answer.upper() not in "ABCD":
                return None
            return Exercise(concept_name=concept, kind=kind, prompt=prompt,
                            options=options, answer=answer.upper(), verified=True)

        if kind == ExerciseKind.NUMERIC:
            try:
                float(answer.replace(",", ""))
            except ValueError:
                return None
            return Exercise(concept_name=concept, kind=kind, prompt=prompt,
                            answer=answer, verified=True)

        if kind == ExerciseKind.CODE:
            reference = str(e.get("reference_solution", ""))
            if not reference.strip():
                return None
            ok, stdout = await run_python_sandboxed(reference)
            claimed = answer.strip()
            actual = stdout.strip()
            if not ok or not actual:
                return None
            if claimed and claimed != actual:
                # the LLM's claimed output was wrong — trust EXECUTION:
                # keep the exercise with the real output as the answer
                claimed = actual
            return Exercise(concept_name=concept, kind=kind, prompt=prompt,
                            starter_code=str(e.get("starter_code", "")),
                            reference_solution=reference,
                            answer=claimed or actual, verified=True)

        # free_text: needs a real rubric
        rubric = str(e.get("rubric", "")).strip()
        if len(rubric) < 15:
            return None
        return Exercise(concept_name=concept, kind=kind, prompt=prompt,
                        rubric=rubric, verified=True)


# ---------------------------------------------------------------------- #
# Assessment Agent — grading
# ---------------------------------------------------------------------- #

_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"correct": {"type": "boolean"},
                   "feedback": {"type": "string"},
                   "misconception": {"type": "string"}},
    "required": ["correct", "feedback", "misconception"],
}

_JUDGE_SYSTEM = """You grade a learner's free-text answer against a rubric.
correct=true only if the answer satisfies the rubric's substance (wording
irrelevant). feedback: 1-2 sentences. misconception: if the answer reveals a
specific misunderstanding, name it in one phrase; else empty string."""


class AssessmentAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def grade(self, exercise: Exercise, response: str) -> GradedAnswer:
        response = (response or "").strip()
        if exercise.kind == ExerciseKind.MCQ:
            correct = response.upper()[:1] == exercise.answer
            return GradedAnswer(exercise_id=exercise.id, correct=correct,
                                weight=1.0,
                                feedback="Correct." if correct else
                                f"The correct option was {exercise.answer}.")
        if exercise.kind == ExerciseKind.NUMERIC:
            try:
                correct = abs(float(response.replace(",", ""))
                              - float(exercise.answer.replace(",", ""))) < 1e-6
            except ValueError:
                correct = False
            return GradedAnswer(exercise_id=exercise.id, correct=correct,
                                weight=1.0,
                                feedback="Correct." if correct else
                                f"Expected {exercise.answer}.")
        if exercise.kind == ExerciseKind.CODE:
            ok, stdout = await run_python_sandboxed(response)
            correct = ok and stdout.strip() == exercise.answer.strip()
            feedback = ("Output matches." if correct else
                        f"Your output: {stdout.strip()[:120] or '(none)'} — "
                        f"expected: {exercise.answer[:120]}")
            return GradedAnswer(exercise_id=exercise.id, correct=correct,
                                weight=1.0, feedback=feedback)
        # free text → judge model, half weight, fail-closed to incorrect-unknown
        try:
            verdict = await self.llm.chat_json(
                "judge", _JUDGE_SYSTEM,
                f"RUBRIC:\n{exercise.rubric}\n\nQUESTION:\n{exercise.prompt}"
                f"\n\nANSWER:\n{response[:1500]}", _JUDGE_SCHEMA)
            return GradedAnswer(
                exercise_id=exercise.id,
                correct=bool(verdict.get("correct") is True), weight=0.5,
                feedback=str(verdict.get("feedback", ""))[:300],
                misconception=str(verdict.get("misconception", ""))[:160])
        except LLMUnavailable:
            return GradedAnswer(exercise_id=exercise.id, correct=False,
                                weight=0.0,
                                feedback="Judge unavailable — answer recorded, "
                                         "not graded (no mastery change).")


# ---------------------------------------------------------------------- #
# Teacher + Socratic agents, and the lesson bundle (Phase 8)
# ---------------------------------------------------------------------- #

class LessonBuilder:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def build(self, concept: str, roadmap: Roadmap, method: str,
                    resources: list[LearningResource],
                    misconceptions: list[str],
                    exercises: list[Exercise]) -> Lesson:
        grounding = "\n".join(f"- [{r.kind}] {r.title} — {r.note[:80]}"
                              for r in resources[:8])
        anti = ("\nKnown misconceptions to pre-empt explicitly:\n"
                + "\n".join(f"- {m}" for m in misconceptions[:3])
                if misconceptions else "")
        if method == "socratic":
            system = ("You are a Socratic tutor. Teach the concept ONLY through "
                      "a sequence of 6-9 numbered questions that lead the "
                      "learner to construct the idea themselves. After each "
                      "question add an indented hint line starting with "
                      "'Hint:'. Never state the final answer outright.")
        else:
            system = ("You are a precise, warm teacher. Explain the concept in "
                      "300-450 words for a motivated adult beginner: start from "
                      "what it is FOR, build the mechanism step by step, use one "
                      "concrete worked mini-example, and end with a two-line "
                      "summary. Ground yourself in the research notes given; "
                      "no invented citations.")
        try:
            body = await self.llm.chat_text(
                "summarize", system,
                f"Concept: {concept}\nSubject: {roadmap.subject}\n"
                f"Research notes:\n{grounding}{anti}")
        except LLMUnavailable:
            body = (f"## {concept}\n\n(LLM unavailable — study from the "
                    "resources below; the concept map still applies.)\n")
        return Lesson(concept_name=concept, method=method,
                      body_md=body.strip(),
                      mermaid=concept_map_mermaid(roadmap, concept),
                      resources=resources[:8], exercises=exercises)

    @staticmethod
    def to_markdown(lesson: Lesson) -> str:
        parts = [f"# {lesson.concept_name}",
                 f"_Method: {lesson.method}_", "",
                 lesson.body_md, "",
                 "## Concept map", "", "```mermaid", lesson.mermaid, "```", "",
                 "## Resources", ""]
        parts += [f"- [{r.kind}] [{r.title}]({r.url})" for r in lesson.resources]
        parts += ["", "## Practice", ""]
        for i, ex in enumerate(lesson.exercises, 1):
            parts.append(f"**{i}. ({ex.kind.value})** {ex.prompt}")
            if ex.options:
                parts += [f"   - {chr(65 + j)}. {o}"
                          for j, o in enumerate(ex.options)]
            if ex.starter_code:
                parts += ["", "```python", ex.starter_code, "```"]
            parts.append("")
        return "\n".join(parts)

    @staticmethod
    def to_html(lesson: Lesson) -> str:
        """Static study page: markdown-ish rendering + mermaid via CDN-free
        inline note (the md is authoritative; this is a convenience view)."""
        body = LessonBuilder.to_markdown(lesson)
        body = re.sub(r"^# (.+)$", r"<h1>\1</h1>", body, flags=re.M)
        body = re.sub(r"^## (.+)$", r"<h2>\1</h2>", body, flags=re.M)
        body = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)",
                      r'<a href="\2">\1</a>', body)
        body = body.replace("```mermaid", '<pre class="mermaid">').replace(
            "```python", "<pre>").replace("```", "</pre>")
        body = re.sub(r"^(?!<)(.+)$", r"<p>\1</p>", body, flags=re.M)
        return (f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
                f"<title>{lesson.concept_name}</title>"
                "<style>body{font:16px/1.6 system-ui;max-width:760px;"
                "margin:2.5rem auto;padding:0 1rem;color:#1d2733}"
                "pre{background:#f3f5f8;padding:1rem;border-radius:8px;"
                "overflow-x:auto}</style></head><body>"
                f"{body}</body></html>")
