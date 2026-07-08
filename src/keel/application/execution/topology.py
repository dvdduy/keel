from __future__ import annotations

from collections import defaultdict

from keel.application.execution.plan import ExecutionPlan, PlanStep, PlanValidationError


def topological_order(plan: ExecutionPlan) -> tuple[PlanStep, ...]:
    """Return plan steps in deterministic topological order.

    Tie-break rule: when multiple steps are ready, choose the lowest key first.
    Raises PlanValidationError when a cycle prevents full traversal.
    """

    steps_by_key = {step.key: step for step in plan.steps}

    remaining_dependencies: dict[str, set[str]] = {
        step.key: set(step.depends_on) for step in plan.steps
    }

    dependents_by_key: dict[str, set[str]] = defaultdict(set)
    for step in plan.steps:
        for dependency_key in step.depends_on:
            dependents_by_key[dependency_key].add(step.key)

    ready = sorted(key for key, dependencies in remaining_dependencies.items() if not dependencies)

    ordered: list[PlanStep] = []

    while ready:
        current_key = ready.pop(0)
        ordered.append(steps_by_key[current_key])

        for dependent_key in sorted(dependents_by_key[current_key]):
            remaining_dependencies[dependent_key].remove(current_key)

            if not remaining_dependencies[dependent_key]:
                ready.append(dependent_key)

        ready.sort()

    if len(ordered) != len(plan.steps):
        stuck_keys = tuple(
            sorted(key for key, dependencies in remaining_dependencies.items() if dependencies)
        )
        raise PlanValidationError(
            f"execution plan contains a cycle involving: {', '.join(stuck_keys)}"
        )

    return tuple(ordered)
