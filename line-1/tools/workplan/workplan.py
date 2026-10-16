#!/usr/bin/env python3
"""Bounded, deterministic dependency scheduler. Standard library only; executes no tasks."""
import argparse
import heapq
import json
import math
from pathlib import Path
import sys


def positive(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(label + " must be a finite positive number")
    return value


def plan(data, workers=1, budget=None):
    if type(workers) is not int or not 1 <= workers <= 64:
        raise ValueError("workers must be an integer from 1 to 64")
    if budget is not None:
        positive(budget, "budget")
    if not isinstance(data, dict) or set(data) != {"tasks"}:
        raise ValueError('input must contain exactly a "tasks" array')
    rows = data["tasks"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 500:
        raise ValueError("tasks must contain 1 to 500 tasks")
    tasks = {}
    for row in rows:
        if not isinstance(row, dict) or not {"id", "minutes"} <= set(row) or set(row) - {"id", "minutes", "after"}:
            raise ValueError("each task needs id, minutes, and optionally after")
        name = row["id"]
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise ValueError("task id must be a nonempty string of at most 100 characters")
        if name in tasks:
            raise ValueError("duplicate task id: " + name)
        duration = positive(row["minutes"], "minutes for " + name)
        deps = row.get("after", [])
        if not isinstance(deps, list) or any(not isinstance(x, str) for x in deps) or len(set(deps)) != len(deps):
            raise ValueError("after must be an array of distinct task ids: " + name)
        tasks[name] = (duration, deps)
    children = {name: [] for name in tasks}
    indegree = {name: len(deps) for name, (_, deps) in tasks.items()}
    for name, (_, deps) in tasks.items():
        for dep in deps:
            if dep not in tasks:
                raise ValueError("unknown dependency: " + dep)
            children[dep].append(name)
    ready = [name for name in tasks if indegree[name] == 0]
    heapq.heapify(ready)
    order = []
    remaining = dict(indegree)
    while ready:
        name = heapq.heappop(ready)
        order.append(name)
        for child in children[name]:
            remaining[child] -= 1
            if remaining[child] == 0:
                heapq.heappush(ready, child)
    if len(order) != len(tasks):
        raise ValueError("dependency cycle blocks: " + ", ".join(sorted(n for n in tasks if remaining[n])))
    tail = {}
    for name in reversed(order):
        tail[name] = tasks[name][0] + max((tail[c] for c in children[name]), default=0)
        if not math.isfinite(tail[name]):
            raise ValueError("duration total exceeds numeric range")
    critical = min(tasks, key=lambda n: (-tail[n], n))
    critical_minutes = tail[critical]
    critical_path = [critical]
    while children[critical]:
        critical = min(children[critical], key=lambda n: (-tail[n], n))
        critical_path.append(critical)
    ready = [(-tail[n], n) for n in tasks if indegree[n] == 0]
    heapq.heapify(ready)
    free = list(range(1, workers + 1))
    running = []
    schedule = []
    now = 0
    while ready or running:
        while ready and free:
            _, name = heapq.heappop(ready)
            worker = heapq.heappop(free)
            end = now + tasks[name][0]
            if not math.isfinite(end):
                raise ValueError("schedule exceeds numeric range")
            heapq.heappush(running, (end, name, worker))
            schedule.append({"task": name, "worker": worker, "start": now, "finish": end})
        if running:
            now = running[0][0]
            # Release every simultaneous completion before choosing more work.
            while running and running[0][0] == now:
                _, name, worker = heapq.heappop(running)
                heapq.heappush(free, worker)
                for child in children[name]:
                    indegree[child] -= 1
                    if indegree[child] == 0:
                        heapq.heappush(ready, (-tail[child], child))
    total = sum(v[0] for v in tasks.values())
    if not math.isfinite(total):
        raise ValueError("duration total exceeds numeric range")
    lower = max(critical_minutes, total / workers)
    return {
        "units": "minutes", "workers": workers,
        "method": "nonpreemptive list scheduling; longest downstream duration first; ties by id",
        "schedule": schedule, "finish": now, "critical_path": critical_path,
        "critical_path_minutes": critical_minutes, "lower_bound": lower,
        "budget": budget, "fits_budget": None if budget is None else now <= budget,
        "deadline_verdict": "not_requested" if budget is None else (
            "fits" if now <= budget else "impossible_at_estimates" if lower > budget else "heuristic_misses_not_proven_impossible"),
        "slack": None if budget is None else budget - now,
    }


def demo():
    return {"tasks": [
        {"id": "read-brief", "minutes": 3},
        {"id": "implement", "minutes": 12, "after": ["read-brief"]},
        {"id": "prepare-fixtures", "minutes": 4, "after": ["read-brief"]},
        {"id": "verify", "minutes": 5, "after": ["implement", "prepare-fixtures"]},
        {"id": "write-handoff", "minutes": 2, "after": ["verify"]},
    ]}


def self_test():
    result = plan(demo(), 2, 25)
    assert result["finish"] == 22 and result["fits_budget"]
    assert plan(demo(), 1)["finish"] == 26
    assert plan(demo(), 2, 20)["deadline_verdict"] == "impossible_at_estimates"
    import random
    rng = random.Random(737)
    for _ in range(150):
        rows = [{"id": str(i), "minutes": rng.randint(1, 20),
                 "after": [str(j) for j in range(i) if rng.random() < .15]}
                for i in range(rng.randint(1, 30))]
        data = {"tasks": rows}
        workers = rng.randint(1, 6)
        result = plan(data, workers)
        assert result == plan({"tasks": list(reversed(rows))}, workers)
        indexed = {r["task"]: r for r in result["schedule"]}
        assert len(indexed) == len(rows)
        for row in rows:
            slot = indexed[row["id"]]
            assert slot["finish"] - slot["start"] == row["minutes"]
            assert all(indexed[d]["finish"] <= slot["start"] for d in row["after"])
        for w in range(1, workers + 1):
            slots = sorted((s for s in indexed.values() if s["worker"] == w), key=lambda s: s["start"])
            assert all(a["finish"] <= b["start"] for a, b in zip(slots, slots[1:]))
        assert result["lower_bound"] <= result["finish"]
    for bad in [[], {"tasks": []}, {"tasks": [{"id": "a", "minutes": True}]},
                {"tasks": [{"id": "a", "minutes": 1, "after": ["a"]}]},
                {"tasks": [{"id": "a", "minutes": 1, "after": ["missing"]}]},
                {"tasks": [{"id": "a", "minutes": float("nan")}]},
                {"tasks": [{"id": "a", "minutes": 1}, {"id": "a", "minutes": 2}]}]:
        try:
            plan(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid input accepted")
    print("PASS: demo, deadline checks, invalid inputs, 150 seeded dependency graphs, determinism and resource constraints")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="workspace-local JSON task file (at most 100 KB)")
    source.add_argument("--demo", action="store_true")
    source.add_argument("--self-test", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--budget", type=float)
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
            return 0
        if args.demo:
            data = demo()
        else:
            root = Path.cwd().resolve()
            path = Path(args.input).resolve()
            if not path.is_relative_to(root):
                raise ValueError("input must be inside the current workspace")
            # Open once, then bound the read even if the file changes size.
            with path.open("rb") as handle:
                raw = handle.read(100001)
            if len(raw) > 100000:
                raise ValueError("input exceeds 100 KB")
            data = json.loads(raw)
        result = plan(data, args.workers, args.budget)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if result["fits_budget"] is False else 0
    except (ValueError, OSError, RecursionError, OverflowError) as exc:
        print("workplan: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
