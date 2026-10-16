# ApiDelta

ApiDelta helps an integration worker find potential breaking changes between an old and a new **OpenAPI 3.0.x or 3.1.x JSON description**. It runs offline using Python 3.9+ and only the standard library. It does not execute any operation in a description, fetch references, or access an account.

Run this command from the repository root:

```sh
python3 -B line-4/tools/apidelta/apidelta.py demo
```

The demo uses the real public swarm description bundled in `imd-openapi.json`. It creates a proposed revision **in memory**, removes its capabilities operation, and adds a mandatory `clientVersion` property to its quote request. The output identifies both changes, with escaped JSON-pointer-style locations and **2 breaking findings**. These are deliberate demonstration changes, not evidence of a change to the running service. The demo exits successfully and makes no network request.

## Compare your descriptions

```sh
python3 -B line-4/tools/apidelta/apidelta.py compare line-4/tools/apidelta/imd-openapi.json line-4/tools/apidelta/imd-openapi.json
```

Comparing the capture against itself reports five compared operations and no findings. Substitute two local JSON files for a real upgrade assessment. File paths must resolve inside the current workspace (the current working directory); escaping symlinks are refused. JSON inputs are limited to 1 MiB, 50,000 nodes and 80 levels. Duplicate keys and non-finite numbers are rejected. The tool never reads configuration or environment variables. It has no third-party dependency and no network code.

Add `--output PATH` to create a JSON report at a new workspace path. Existing output files are never overwritten. Reports are deterministic for the same inputs. They include hashes of the exact input bytes, counts by severity, locations, explanations and the number of operations compared.

| Exit | Meaning |
| --- | --- |
| 0 | No detected breakage, or a successful demo |
| 1 | At least one potential breaking change |
| 2 | Invalid input, unsupported reference, resource limit, or file error |
| 3 | No breaking finding, but unresolved changes need review |

In automation, accept only exit 0 and still review the tool's scope. `no_detected_breakage` is a finding about this static subset, **not a compatibility guarantee**. Runtime behavior and undocumented changes are invisible to it.

## What it checks

- Removed and added operations; required and optional parameters, including path-level inheritance and operation overrides.
- Changes to effective authentication requirements and server locations. These require review rather than assuming either is safe.
- Newly mandatory request bodies; request and response media types; response status changes and metadata.
- Request types/enums becoming narrower, response types/enums becoming wider, and the integer/number subtype relationship.
- Newly required request properties, lost required response properties, closed-object changes and nested properties/array items.
- Local object-member `$ref` pointers, including `~0`/`~1` escapes. It resolves **both descriptions independently** so a changed shared component is found even when the reference text stays unchanged. Recursive schema references terminate through comparison-pair tracking.

Changed constraints it cannot evaluate (such as `oneOf`, `allOf`, numeric bounds, regexes, read/write flags and formats) produce **review** findings. Unused components, authentication definitions, vendor extensions, dialect changes and document metadata are conservatively caught by a document-level review finding. Metadata, including descriptions, can therefore produce review findings. Literal values and properties named `description` or `title` are preserved.

This first piece does not implement full schema implication or validate a whole OpenAPI document. It may flag a potential break whose effect is neutralized by another constraint. It does not model generated client behavior, callbacks/webhooks, response headers semantically, parameter content schemas semantically, or server URL equivalence. External references, path-item references, reference alias cycles and `$ref` objects with semantic siblings are refused when analyzed. Inline these before comparing. Only plain fragment pointers through object members are resolved; array-index/percent-encoded reference forms are outside this piece. Unused references are not checked. The description remains untrusted data, and no instructions in it are followed.

Comparison work is bounded to 20,000 schema visits and 2,000 findings. Exceeding a limit returns exit 2 without a partial success report.

## What happened when tried

- Fetched `https://api.imd.fun/openapi.json` on **2026-10-16** with User-Agent `Pepeolithic-ApiDelta/1.0`: HTTP 200, OpenAPI 3.1.0, five operations, **23,132 bytes**. The capture's SHA-256 is `be142840c010710cb2a5b9e5c73e71d8e79ec4054c15661699d60bfa627be96a`. It is a dated observation, not authenticated evidence or a promise of current service behavior.
- Compared the real capture with itself: five operations, no findings, exit 0.
- Ran the offline demo: two intended breaking changes found, exit 0.
- Passed all **44 offline regression tests**, covering reference target changes, recursion, variance, inheritance, escaped locations, limits, command-line exit codes and overwrite refusal.

```sh
python3 -B line-4/tools/apidelta/selftest.py
```

No paid API action, quote, payment, signature, token balance or transaction was requested. The capture contains the service's public descriptions of payments; ApiDelta treats them as metadata and needs no coin. Future pieces can add semantic constraint rules and machine-readable suppressions while preserving this conservative review behavior.
