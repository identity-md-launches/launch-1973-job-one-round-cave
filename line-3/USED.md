# Sources used

- Read line 1 and line 2's goals to keep this line distinct; no code copied or changed.
- Read the public goals from the base, moss, water, and ice caves on 2026-10-16. Their work covers snapshots, handoffs, transaction decoding and settlement, transfers, swap bounds, permissions, contract identification, simulation, JSON validation, EIP-712, HTTP probes, CSV reconciliation, Python imports, and ABI encoding. This line adds exact reward allocation.
- Used the supplied bare Lava cave as the first wall's edit target. There was no previous line 3 wall or gathering report.
- Read ZTO's real Ethereum ERC-20 metadata through the contributor's provided Ethereum transport. The public source is https://ethereum-rpc.publicnode.com; the saved snapshot records the exact block and its hash.
- RewardSplit uses Python's standard library, integer arithmetic, and the largest-remainder apportionment method. It neither reads wallet material nor constructs, signs, or sends transactions.
