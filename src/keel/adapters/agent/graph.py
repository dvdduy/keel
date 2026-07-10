from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from keel.application.agent.diagnose import Diagnosis, diagnose
from keel.application.agent.dossier import IncidentDossier, assemble_dossier
from keel.application.incident.model import Incident
from keel.application.ports.platform_reader import PlatformReader


class AgentState(TypedDict, total=False):
    incident: Incident
    dossier: IncidentDossier
    diagnosis: Diagnosis


async def _reason(state: AgentState) -> AgentState:
    return {"diagnosis": diagnose(state["dossier"])}


def build_incident_agent(reader: PlatformReader) -> Any:
    async def gather(state: AgentState) -> AgentState:
        return {"dossier": await assemble_dossier(state["incident"], reader)}

    graph = StateGraph(AgentState)
    graph.add_node("gather", gather)
    graph.add_node("reason", _reason)
    graph.set_entry_point("gather")
    graph.add_edge("gather", "reason")
    graph.add_edge("reason", END)
    return graph.compile()
