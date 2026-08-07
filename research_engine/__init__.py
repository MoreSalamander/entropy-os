"""research-engine — General Research Intelligence Engine.

Three foundational systems:
  1. Parallel Research Engine  (planner + async source fan-out + evidence extraction)
  2. Context Graph             (per-session situational awareness, DataHub-emitted)
  3. Knowledge Graph           (persistent cross-session intelligence)

Design law (MoreSalamander deterministic-scaffold thesis): LLMs propose,
deterministic code decides. Every claim is source-linked evidence or it does
not enter a graph. Verification gates sit between session context and
persistent knowledge. Nothing is fabricated to fill a report section — empty
sections say so.
"""

__version__ = "0.1.0"
