"""CLI.

  python -m entropy_os.engines.university study "Teach me machine learning" --steps 3
      run a study session: roadmap → research → N adaptive activities.
      Interactive by default (answers typed at the prompt); --auto simulates
      a learner (answers MCQ/numeric/code correctly with --auto-correct
      probability) for demos and pipelines.

  python -m entropy_os.engines.university report <learner_json>   mastery report
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from pathlib import Path

from .engine import LearnEngine, mastery_report
from .models import ExerciseKind


async def _main() -> int:
    parser = argparse.ArgumentParser(prog="entropy_os.engines.university")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("study")
    s.add_argument("goal")
    s.add_argument("--steps", type=int, default=3)
    s.add_argument("--auto", action="store_true",
                   help="simulated learner (no prompts)")
    s.add_argument("--auto-correct", type=float, default=0.7,
                   help="probability the simulated learner answers correctly")
    s.add_argument("--seed", type=int, default=29)
    r = sub.add_parser("report")
    r.add_argument("learner_json", type=Path)
    args = parser.parse_args()

    if args.cmd == "report":
        from .models import LearnerProfile, Roadmap
        data = json.loads(args.learner_json.read_text())
        profile = LearnerProfile.model_validate(data)
        print(json.dumps({k: v.level.value for k, v in profile.mastery.items()},
                         indent=2))
        return 0

    rng = random.Random(args.seed)
    engine = LearnEngine()
    try:
        roadmap = await engine.start(args.goal)
        for _step in range(args.steps):
            activity = await engine.next()
            if activity is None:
                break
            answers: dict[str, str] = {}
            for ex in activity.exercises:
                if args.auto:
                    answers[ex.id] = _simulate(ex, rng, args.auto_correct)
                else:
                    print(f"\n--- {ex.kind.value}: {ex.prompt}")
                    for j, opt in enumerate(ex.options):
                        print(f"  {chr(65 + j)}. {opt}")
                    if ex.starter_code:
                        print(ex.starter_code)
                    answers[ex.id] = input("your answer> ")
            await engine.submit(activity, answers)
        await engine.finish()
        print("\n" + mastery_report(engine.profile, roadmap))
        print(f"\nsession: {engine.storage / 'sessions' / (engine.session_id + '.json')}")
    finally:
        await engine.aclose()
    return 0


def _simulate(ex, rng: random.Random, p_correct: float) -> str:
    """Scripted learner: answers correctly with probability p_correct.
    Wrong answers are plausibly wrong (adjacent option, off-by-one number,
    broken code) so grading and misconception paths get exercised."""
    correct = rng.random() < p_correct
    if ex.kind == ExerciseKind.MCQ:
        if correct:
            return ex.answer
        wrong = [c for c in "ABCD" if c != ex.answer]
        return rng.choice(wrong)
    if ex.kind == ExerciseKind.NUMERIC:
        if correct:
            return ex.answer
        try:
            return str(float(ex.answer.replace(",", "")) + 1)
        except ValueError:
            return "0"
    if ex.kind == ExerciseKind.CODE:
        if correct:
            return ex.reference_solution
        return "print('wrong answer')"
    # free_text: simulated learner writes something rubric-shaped or vague
    return (f"A reasonable explanation touching on {ex.concept_name}."
            if correct else "I am not sure.")


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
