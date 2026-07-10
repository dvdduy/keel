from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from keel.application.agent.diagnose import Diagnosis


class RunbookNarrator(Protocol):
    async def narrate(self, diagnosis: Diagnosis) -> Diagnosis: ...
