"""Resource-constrained critical-path scheduling.

Given a set of task assignments (each task already mapped to a worker), this
module computes a realistic schedule that:

* respects task **dependencies** (a task cannot start until every task it
  depends on has finished), and
* respects each **worker as a single resource** (a worker can only do one
  task at a time, so their tasks are serialised).

From that schedule it derives the project **duration** and the **critical
path** - the chain of tasks that actually determines the finish time,
including waits caused by a worker being busy, not just dependency waits.

The algorithm is a deterministic *list schedule*:

1. Topologically order the tasks (ties broken by priority, then name).
2. Walk that order, giving each task the earliest start that satisfies both
   its dependencies and its worker's availability.
3. Backtrack from the last-finishing task to recover the critical path.

Everything here is deterministic - the same assignments always yield the
same schedule.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from models import Assignment


def _topological_order(assignments: List[Assignment]) -> List[Assignment]:
    """Return assignments in dependency order (Kahn's algorithm).

    Ties between ready tasks are broken by ``(priority, task name)`` so the
    ordering - and therefore the whole schedule - is deterministic. Only
    dependencies that exist in this task set are considered; references to
    unknown tasks are ignored.
    """
    by_name = {a.task: a for a in assignments}
    # Count only dependencies that are present in this set.
    indegree = {
        a.task: sum(1 for d in a.dependencies if d in by_name) for a in assignments
    }
    # Build dependents map: dep -> [tasks that depend on it].
    dependents: Dict[str, List[str]] = {a.task: [] for a in assignments}
    for a in assignments:
        for d in a.dependencies:
            if d in by_name:
                dependents[d].append(a.task)

    def sort_key(name: str):
        a = by_name[name]
        return (a.priority, a.task)

    ready = sorted(
        (name for name, deg in indegree.items() if deg == 0), key=sort_key
    )
    order: List[Assignment] = []
    while ready:
        name = ready.pop(0)
        order.append(by_name[name])
        for child in dependents[name]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort(key=sort_key)

    # If a dependency cycle left tasks unprocessed, append them in a stable
    # order so the scheduler still produces output rather than dropping them.
    if len(order) < len(assignments):
        remaining = [a for a in assignments if a not in order]
        remaining.sort(key=lambda a: (a.priority, a.task))
        order.extend(remaining)
    return order


def schedule(assignments: List[Assignment]) -> Dict[str, object]:
    """Compute start/finish times, duration, and the critical path.

    Mutates each assignment in place to set ``start_time``, ``finish_time``,
    and ``is_on_critical_path``. Unassigned tasks (no worker, e.g. a missing
    skill) are left unscheduled.

    Returns a dict with ``duration`` (project finish time) and
    ``critical_path`` (an ordered list of task names).
    """
    by_name = {a.task: a for a in assignments}
    order = _topological_order(assignments)

    # When each worker next becomes free, and which task they last finished.
    worker_free: Dict[str, float] = {}
    worker_last_task: Dict[str, Optional[str]] = {}
    # For critical-path backtracking: the task that caused this task's start.
    predecessor: Dict[str, Optional[str]] = {}

    for a in order:
        if a.assigned_to is None:
            # Cannot schedule work nobody is doing.
            predecessor[a.task] = None
            continue

        worker = a.assigned_to

        # Earliest start allowed by dependencies (only scheduled ones count).
        dep_finish = 0.0
        binding_dep: Optional[str] = None
        for d in a.dependencies:
            dep_a = by_name.get(d)
            if dep_a is not None and dep_a.finish_time is not None:
                if dep_a.finish_time > dep_finish:
                    dep_finish = dep_a.finish_time
                    binding_dep = d

        # Earliest start allowed by the worker being free.
        resource_free = worker_free.get(worker, 0.0)

        start = max(dep_finish, resource_free)
        finish = start + a.assigned_hours

        a.start_time = start
        a.finish_time = finish

        # Record what determined this task's start (for the critical path).
        if dep_finish >= resource_free and binding_dep is not None and dep_finish > 0:
            predecessor[a.task] = binding_dep
        elif resource_free > 0 and worker_last_task.get(worker) is not None:
            predecessor[a.task] = worker_last_task[worker]
        else:
            predecessor[a.task] = None  # started at time 0

        worker_free[worker] = finish
        worker_last_task[worker] = a.task

    # Project duration = latest finish among scheduled tasks.
    scheduled = [a for a in assignments if a.finish_time is not None]
    if not scheduled:
        return {"duration": 0.0, "critical_path": []}

    last = max(scheduled, key=lambda a: (a.finish_time, -a.priority, a.task))
    duration = last.finish_time

    # Backtrack the critical path from the last task.
    critical: List[str] = []
    cursor: Optional[str] = last.task
    guard = 0
    while cursor is not None and guard <= len(assignments):
        critical.append(cursor)
        by_name[cursor].is_on_critical_path = True
        cursor = predecessor.get(cursor)
        guard += 1
    critical.reverse()

    return {"duration": duration, "critical_path": critical}
