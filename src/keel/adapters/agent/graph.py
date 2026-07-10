from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from keel.application.agent.diagnose import Diagnosis, diagnose
from keel.application.agent.dossier import IncidentDossier, assemble_dossier
from keel.application.agent.runbook import narrate_runbook
from keel.application.incident.model import Incident
from keel.application.ports.platform_reader import PlatformReader
from keel.application.ports.runbook_narrator import RunbookNarrator


class AgentState(TypedDict, total=False):
    incident: Incident
    dossier: IncidentDossier
    diagnosis: Diagnosis


def build_incident_agent(reader: PlatformReader, narrator: RunbookNarrator | None = None) -> Any:
    async def gather(state: AgentState) -> AgentState:
        return {"dossier": await assemble_dossier(state["incident"], reader)}

    async def reason(state: AgentState) -> AgentState:
        diagnosis = diagnose(state["dossier"])
        if narrator is not None:
            diagnosis = await narrate_runbook(diagnosis, narrator)
        return {"diagnosis": diagnosis}

    graph = StateGraph(AgentState)
    graph.add_node("gather", gather)
    graph.add_node("reason", reason)
    graph.set_entry_point("gather")
    graph.add_edge("gather", "reason")
    graph.add_edge("reason", END)
    return graph.compile()
