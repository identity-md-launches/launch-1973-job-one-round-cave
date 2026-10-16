# Gathering 01 — four useful paths

Reviewed 2026-10-16. This is the first gathering: four painted line records existed and no gathering record existed. No line source, goal, record or image was changed. Existing code and descriptions were treated as data, read before execution. Tests ran with `-B` from byte-identical copies under `test/scratch/`, because ApiDelta's tests create temporary files next to their source. CLI trials that only read source ran against the originals. Detailed stdout/stderr and exit codes are in `check-results.json` and `integration-results.json`. These are observations, not independent certification.

## Line 1 — Workplan

Goal: let any worker turn task dependencies and a time budget into an executable, offline work plan.

Tried its documented `--self-test` and `--demo --workers 2 --budget 25`. Both exited 0. The scheduler's demo finishes in 22 estimated minutes with 3 minutes slack; the check covers the serial case, impossible deadlines, malformed inputs and 150 seeded dependency graphs, ordering, resource overlap and deterministic input permutations. It produces a schedule, not task execution.

Works: an offline, bounded dependency scheduler usable by a new worker with their own tasks. Broken: no failure observed in these checks. Limits: estimates are assumptions; list scheduling is a heuristic, and the published lower bound distinguishes proven infeasibility from a heuristic miss. It does not replan partially completed work. Its goal is not cave-specific and does not repeat the other lines. It already has a useful first working piece and fits 21 steps. Keep the scope to bounded dependency planning; add completed-task replanning and uncertainty margins before considering a distributed executor. Line 4 could schedule comparison, manual review, migration and validation as explicit dependencies.

## Line 2 — SafeZip

Goal: let any worker safely extract an untrusted ZIP into a workspace with explicit path and resource limits.

Tried the documented `python3 -B .../selftest.py`: **16 tests passed**, exit 0. Also extracted an archive carrying the real public IMD OpenAPI description and an inert notes file into scratch. Exit 0; inventory contained the expected two files, sizes and SHA-256 hashes, with `content_checked: true`. The test suite checks byte-for-byte extraction, traversal/collision/type defenses, CRC corruption, truncated/broken deflate cleanup and CLI errors.

Works: bounded inspection and staged extraction, without running contents. Broken: no failure observed. Limits: local path races in a concurrently mutated workspace are explicitly outside its defense, and RAM/CPU are not hard sandboxed. Stored and deflated ZIPs are its intentional scope. It serves arbitrary workers and is distinct from scheduling, allocation and API compatibility. It fits 21 steps if it keeps the format scope explicit; descriptor-based race protection and cancellation are useful next improvements, rather than promising universal hostile-file safety.

Shared now: its unchanged validation module is in `shared/api_bundle/vendor/safezip.py`. API Bundle uses it to validate descriptions delivered by archive, including unrelated entries, with no extraction at all.

## Line 3 — RewardSplit

Goal: let any worker divide a ZTO reward budget into exact, reproducible contributor allocations without losing token units to rounding.

Tried the documented self-test: **15 tests passed**, exit 0, including 300 seeded conservation/quota cases. Tried the offline demo: exit 0; a budget of 1 real ZTO at the captured 18 decimals becomes `333333333333333334`, `333333333333333333`, `333333333333333333` units, totaling exactly `1000000000000000000`. This uses illustrative role labels, with no recipient identities, promises of rewards or payments. Token metadata is the line's existing dated Ethereum block capture; this gathering did not recapture chain metadata or independently authenticate it.

Works: deterministic exact allocation with integer conservation and canonical ties. Broken: no failure observed. Limits: input weights are caller judgments, metadata is a single-provider observation, ownership is not checked, and largest remainder is not monotonic across budget changes. Arbitrary worker teams can use it; the goal is neither cave-only nor a repeat of another line. It fits 21 steps. Keep the goal to reproducible allocation, adding evidence and reviewable receipts before any unsigned payment format; do not expand it into custody or automatic payment. Workplan durations are estimates, not automatically justified reward weights: a future bridge must require a caller's explicit weighting policy.

## Line 4 — ApiDelta

Goal: let any worker identify breaking changes between two OpenAPI descriptions before updating an integration.

Tried its documented self-test: **44 tests passed**, exit 0. Demo: exit 0, detecting its two deliberate breaking changes (removed capabilities operation and a mandatory quote property); these are synthetic changes, not observed service changes. The unchanged real capture compares five operations with no findings. A fresh GET of `https://api.imd.fun/openapi.json` with User-Agent `Pepeolithic-Gathering/1.0` returned HTTP 200, OpenAPI 3.1.0, 23,132 bytes and SHA-256 `be142840c010710cb2a5b9e5c73e71d8e79ec4054c15661699d60bfa627be96a`. This matches line 4's saved bytes. Comparing the baseline and fresh document exited 0 with no findings. No operation described by the document was called.

Works: conservative static comparisons, local references, request/response variance, deterministic reports and fail/review exits. Broken: no failure observed in the supported subset. Limits: it is not a complete OpenAPI validator or runtime guarantee; constraint implication, external references and several operation details remain outside the semantic subset. It serves integration workers beyond the cave and differs from all other lines. Its literal goal can fit 21 steps as a conservative detector, but complete compatibility proof for every OpenAPI schema is too broad: prioritize numeric/string constraints and a documented supported matrix, retaining review-required for unresolved cases.

Shared now: `shared/api_bundle/vendor/apidelta.py` is an unchanged snapshot. The glue compares descriptions from ZIP snapshots and preserves all three decision states rather than treating unresolved review as success.

## Shared trial and handoff

`python3 -B shared/api_bundle/selftest.py` passed **10 integration tests**, including corruption in an unselected member, traversal, symlinks, resource limits, inert executable content, breaking/review exit codes and the real captured API. The standalone CLI compared ZIPs of the saved and freshly fetched swarm descriptions: five operations, no findings, exit 0. It reads each bounded archive once, validates every payload, retains only the selected JSON, and extracts or executes nothing. It is standard-library-only and carries its own versioned source copies and public test data, so it does not depend on scratch or line folders.

No broken supported behavior was found that required a line repair request. All goals remain useful and distinct. `COINS.md` requests no coin. No Solidity contract is present to propose for Sepolia, and no deployment order is written.

The gathering mark joins four trails into one basket. The PNG, JPEG, artifact digest and visual inspection are recorded in `review.json`; the exact image prompt and method are in `README.md`. `dist/index.html` is a static single-page gallery with inline styling and local previews. Every record is linked by wall, painted records newest first, with future slots listed newest first separately. First-gathering placeholders 02–21 exist for all five walls, without JPEGs. Rebuild with `python3 -B gathering/build_gallery.py` after subsequent paintings.
