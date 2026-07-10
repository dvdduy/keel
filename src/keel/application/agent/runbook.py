from __future__ import annotations

from dataclasses import replace

from keel.application.agent.diagnose import Diagnosis
from keel.application.ports.runbook_narrator import RunbookNarrator


async def narrate_runbook(diagnosis: Diagnosis, narrator: RunbookNarrator) -> Diagnosis:
    narrated = await narrator.narrate(diagnosis)
    if len(narrated.runbook) != len(diagnosis.runbook):
        return diagnosis
    return replace(diagnosis, runbook=narrated.runbook)
