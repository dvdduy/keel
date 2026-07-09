from __future__ import annotations

from keel.application.incident.model import Incident, IncidentRoute


def route_incident(incident: Incident) -> IncidentRoute:
    """Derive the owning team route from the immutable incident snapshot."""
    return IncidentRoute(team=incident.team, owner=incident.owner)
