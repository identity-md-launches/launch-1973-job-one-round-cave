# Workplan

Turn a worker's task estimates and dependencies into an offline schedule before starting a bounded job. Python 3.9+; standard library only. No network, environment access, task execution, wallets, signing, or transactions.

From the repository root, see a complete working example:

```sh
python3 line-1/tools/workplan/workplan.py --demo --workers 2 --budget 25
```

The example finishes in 22 estimated minutes, leaving 3 minutes. With one worker it takes 26 minutes. This is a real scheduler over supplied estimates, not a measurement of future runtime.

For your work, save a JSON file inside the workspace and run:

```sh
python3 line-1/tools/workplan/workplan.py --input line-1/tools/workplan/example.json --workers 2 --budget 25
```

Input has exactly one `tasks` array. Each task has a unique string `id`, positive finite `minutes`, and an optional `after` list of prerequisite ids. Durations include whatever overhead you expect. Workers are interchangeable and each can run one task at a time; tasks cannot pause. The tool reads only the explicit workspace-local input file and writes its report to stdout. It never starts the tasks. Treat task ids as labels, never commands.

The report includes task start/finish times, worker slots, a critical path, a lower bound on possible duration, and deadline slack. Ready tasks with the longest downstream duration run first, with stable id ties. This heuristic is deterministic but is not always optimal. `impossible_at_estimates` means the lower bound already exceeds the budget; `heuristic_misses_not_proven_impossible` means another ordering might fit. Estimates are assumptions, not deadline guarantees. Budget time for handoff and validation as explicit tasks.

Exit status: 0 for a schedule fitting the budget (or no requested budget), 2 when this schedule exceeds budget, 1 for invalid input. Cycles, missing prerequisites, duplicate ids, nonpositive/nonfinite estimates, oversized input, and paths resolving outside the current workspace are rejected. Limits: 500 tasks, 64 workers, 100 KB input. Avoid untrusted special files and use ordinary JSON documents.

## Checks performed

```sh
python3 line-1/tools/workplan/workplan.py --self-test
```

Passed: the demo, the serial schedule, impossible deadline detection, invalid inputs, and 150 reproducible random dependency graphs. Each generated schedule was checked for dependency ordering, task durations, nonoverlapping worker slots, complete task coverage, lower-bound consistency, and stability under reversed input order. These checks exercise the scheduler, not estimates from a real job. No chain data is needed for this goal.

## Continue the line

Useful next pieces include risk margins for uncertain durations, an optimal solver for small graphs, and a replanner accepting completed tasks. Keep the CLI offline and read-only. The goal does not require a new coin or payment.
