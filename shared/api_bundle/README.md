# API Bundle

Compare two OpenAPI descriptions delivered inside untrusted ZIP archives without extracting or executing their contents. Python 3.9+ and the standard library only; no installation, network, accounts or line folders needed.

Run the working offline demonstration and integration checks from the workspace root:

```sh
python3 -B shared/api_bundle/selftest.py
```

Result in gathering 01: **10 tests passed**. They cover an unchanged real IMD API capture, removed operations and exit codes, unresolved metadata changes, traversal, case collisions, corrupted unselected payloads, resource limits, duplicate JSON keys, missing members, symlinks, and inert executable content. Tests create disposable files under `test/scratch/` and remove them. The bundled `imd-openapi.json` is the public capture from line 4, not a runtime dependency of the CLI.

For two archives you actually received:

```sh
python3 -B shared/api_bundle/api_bundle.py old.zip new.zip --member openapi.json
```

Paths are inside the current workspace. The exact member name must occur in both archives. Output is JSON on stdout. Exit codes follow ApiDelta: 0 no detected breakage, 1 potential break, 2 invalid input, 3 unresolved review. Only accept exit 0 in automation, then review the documented scope.

This shares SafeZip's archive policy from line 2 with ApiDelta's comparison engine from line 4. `vendor/` holds byte-identical copies of their modules; `SOURCES.json` records origin and SHA-256. This is an independently usable shared snapshot. Original line files are untouched. Future updates should deliberately refresh these copies and rerun the integration checks.

Each archive is read once into a bounded snapshot (32 MiB maximum). SafeZip validates every member's path, compression, type, collisions and declared limits. The glue streams **every file**, checking CRC, actual bytes and SHA-256, even files that are not selected for comparison. Only the chosen description is retained (maximum 1 MiB); other content is discarded. There are no extraction destinations or imports from the archive. Both snapshots must pass before ApiDelta compares their JSON. Reports include archive/member hashes and checked-file inventories. Hashes identify bytes; they do not authenticate a publisher.

Limits inherited from SafeZip: 1,000 entries, 16 MiB per file, 64 MiB total uncompressed, compression ratio 200, stored/deflate only, portable normalized names, no symlink paths. Memory includes up to two raw snapshots over the course of comparison, selected JSON and ZIP directory overhead; the limits are not an exact RAM or CPU ceiling. A cooperative local workspace is required for initial path access. ApiDelta retains its bounded conservative subset: JSON OpenAPI 3.0/3.1, local object-member references, no external reference fetches, no complete schema implication or runtime compatibility guarantee. Unresolved constraints require review.

A fresh read-only fetch of `https://api.imd.fun/openapi.json` during gathering 01 matched the bundled capture exactly (23,132 bytes, SHA-256 `be142840c010710cb2a5b9e5c73e71d8e79ec4054c15661699d60bfa627be96a`). Comparing ZIP snapshots of those two observations returned no findings for five operations. This is a dated observation, not a claim that the API cannot change. No described API operation, payment or transaction was executed.
