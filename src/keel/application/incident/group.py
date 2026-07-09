from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from keel.application.incident.model import Incident
from keel.application.lineage.graph import LineageGraph


@dataclass(frozen=True)
class IncidentGroup:
    roots: tuple[Incident, ...]
    correlated: tuple[Incident, ...]


def group_incidents(
    incidents: Iterable[Incident],
    graph: LineageGraph,
) -> tuple[IncidentGroup, ...]:
    incident_list = tuple(incidents)
    incidents_by_subject: dict[str, list[Incident]] = {}

    for incident in incident_list:
        incidents_by_subject.setdefault(incident.subject, []).append(incident)

    breaching_subjects = frozenset(incidents_by_subject)
    visited: set[str] = set()
    groups: list[IncidentGroup] = []

    for subject in sorted(breaching_subjects):
        if subject in visited:
            continue

        component = _component(subject, breaching_subjects, graph)
        visited.update(component)

        roots: list[Incident] = []
        correlated: list[Incident] = []

        for component_subject in component:
            target = correlated if graph.feeds(component_subject) & breaching_subjects else roots
            target.extend(incidents_by_subject[component_subject])

        groups.append(
            IncidentGroup(
                roots=tuple(sorted(roots, key=_incident_key)),
                correlated=tuple(sorted(correlated, key=_incident_key)),
            )
        )

    return tuple(sorted(groups, key=_group_key))


def _component(
    subject: str,
    breaching_subjects: frozenset[str],
    graph: LineageGraph,
) -> frozenset[str]:
    visited: set[str] = set()
    frontier = [subject]

    while frontier:
        current = frontier.pop()
        if current in visited:
            continue

        visited.add(current)
        connected = (graph.impacted_by(current) | graph.feeds(current)) & breaching_subjects
        frontier.extend(sorted(connected - visited, reverse=True))

    return frozenset(visited)


def _incident_key(incident: Incident) -> tuple[str, str]:
    return (incident.subject, incident.slo_name)


def _group_key(group: IncidentGroup) -> tuple[str, str]:
    incidents = group.roots if group.roots else group.correlated
    return min(_incident_key(incident) for incident in incidents)
