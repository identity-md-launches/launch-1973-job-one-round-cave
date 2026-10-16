# RewardSplit

RewardSplit divides a ZTO budget among contributor weights using exact integer units and largest-remainder apportionment. No token unit disappears into rounding. It is Python 3.9+ using only the standard library, and works offline with the included real Ethereum token metadata.

From the repository root, run:

```sh
python3 -B line-3/tools/rewardsplit/rewardsplit.py demo
```

This demonstration allocates **1 ZTO**, with its real 18 decimals, among three illustrative task roles. `build` receives `333333333333333334` units; `research` and `review` each receive `333333333333333333`. Their sum is exactly `1000000000000000000`. These are role labels, not recipient identities. The demo has no recipient addresses and creates no payment.

## Allocate your own budget

Copy `example.json` to a file inside your workspace. Supply your actual budget and contributor IDs/weights, then run:

```sh
python3 -B line-3/tools/rewardsplit/rewardsplit.py allocate --input line-3/tools/rewardsplit/example.json
```

The input has exactly two keys: `budget` (a decimal **string**) and `contributors` (1–1000 objects). Each contributor has an ASCII `id`, a decimal-string `weight`, and optionally their actual Ethereum `address`. No address is invented when one is omitted. Zero weights are allowed; at least one weight must be positive. Duplicate IDs and duplicate supplied addresses are rejected. Use strings even for whole numbers: `"1"`, not `1`.

Budgets must fit uint256 after conversion to token units. Excess precision, exponents, negative values, floating-point values, and zero budgets fail. Weights support up to 18 whole and 18 fractional decimal digits. Outputs use decimal strings for token amounts so JSON consumers cannot silently round large integers.

Each exact proportional share is first rounded down. Remaining units go to the largest fractional remainders; equal remainders are ordered by contributor ID in ASCII order. Output rows use that same canonical ID order, so permuting input rows does not change the report. Each allocation is within one smallest token unit of its exact share. Zero-weight contributors receive zero. ID choice therefore matters when fractions tie. Freeze IDs and the budget before allocating; largest-remainder apportionment does not guarantee that every individual's amount increases when the overall budget changes.

`--output PATH` writes JSON to a new file and refuses to overwrite an existing file. File inputs and outputs must resolve inside the current working directory. Run from the workspace root. The output is an allocation report, not executable calldata, a balance assertion, gas estimate, or evidence that anybody has been paid. Optional addresses are parsed syntactically and normalized to lowercase; ownership and checksums are not verified.

## Refresh token metadata (optional, read only)

```sh
python3 -B line-3/tools/rewardsplit/rewardsplit.py inspect --output line-3/tools/rewardsplit/zto-fresh.json
```

This defaults to ZTO and the public Ethereum endpoint `https://ethereum-rpc.publicnode.com`. `--token imd` selects the real IMD contract; allocate against its capture using `--metadata PATH`. `--rpc URL` selects a read transport, and `--source URL` records its public provenance if a relay is used. On the assignment machine the supplied contributor transport was used, with the public endpoint named as provenance. No local transport address is embedded in the capture.

Inspection calls only `eth_chainId`, `eth_blockNumber`, `eth_getBlockByNumber`, and `eth_call`. Metadata calls are pinned to one numeric block and its hash is checked again afterward to detect a reorganization during capture. Every HTTP request has its own User-Agent, a 20-second timeout, and a 256-KiB response cap. Redirects and environment proxy discovery are disabled. No wallet, key, configuration file, environment variable, or signing/sending API is used. This is a single-provider observation, not an independent chain proof. A modified metadata file is not authenticated by the allocator.

## What happened when tried

- Live Ethereum capture: block **26205319**, hash `0xa4d2f8165b2b090fe930545d71b952c06e02401f56a892caf8d6f7a8a47d8a9a`, ZTO (`Zero To One`), 18 decimals, total supply `1000000000000000000000000000` units. The exact observation is in `zto-mainnet.json`.
- Offline demo: allocated exactly 1 ZTO, distributed its one rounding unit deterministically, and left zero units unallocated.
- Offline self-test: all **15 tests passed**, including 300 seeded cases checking conservation and proportional-share bounds, permutations, zero weights, uint256 limits, malformed inputs, 1000 contributors, wrong-chain rejection, and a simulated block reorganization.

Run the tests without network access:

```sh
python3 -B line-3/tools/rewardsplit/selftest.py
```

The tool has no third-party dependencies. Later work can add caller-supplied contributor evidence or an independently reviewed unsigned payment format while retaining this allocation core.
