from __future__ import annotations

from keel.application.agent.diagnose import Diagnosis
from keel.application.agent.guardrails import enforce_narration, redact_for_narration
from keel.application.ports.runbook_narrator import RunbookNarrator


async def narrate_runbook(diagnosis: Diagnosis, narrator: RunbookNarrator) -> Diagnosis:
    safe = redact_for_narration(diagnosis)
    narrated = await narrator.narrate(safe)
    return enforce_narration(safe, narrated)
