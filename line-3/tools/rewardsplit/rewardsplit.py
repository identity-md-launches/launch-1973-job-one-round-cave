#!/usr/bin/env python3
"""Exact ERC-20 reward allocation. Standard library only; no signing or sending."""

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


PUBLIC_RPC = "https://ethereum-rpc.publicnode.com"
TOKENS = {
    "zto": "0xd782bdea4ef02a0bd391eb9089470c8080f0a68e",
    "imd": "0xd34a99bc0f67ae1bbd63c660e6d0b0dd03e263b7",
}
UINT256_MAX = (1 << 256) - 1
MAX_BYTES = 262144
MAX_CONTRIBUTORS = 1000
USER_AGENT = "Pepeolithic-RewardSplit/1.0"


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def workspace_path(value):
    path = Path(value).resolve()
    require(path.is_relative_to(Path.cwd().resolve()), "file must be within the current workspace")
    return path


def object_pairs(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, "duplicate JSON key: " + key)
        obj[key] = value
    return obj


def parse_json(data):
    try:
        return json.loads(data, object_pairs_hook=object_pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(Invalid("non-finite JSON value")))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise Invalid("invalid JSON") from exc


def read_json(value):
    with workspace_path(value).open("rb") as source:
        data = source.read(MAX_BYTES + 1)
    require(len(data) <= MAX_BYTES, "JSON input exceeds byte limit")
    return parse_json(data)


def write_json(value, destination=None):
    result = json.dumps(value, indent=2, ensure_ascii=True) + "\n"
    if destination:
        path = workspace_path(destination)
        # Refuse overwrites so a report cannot destroy a worker's input or code.
        with path.open("x", encoding="utf-8") as output:
            output.write(result)
    else:
        sys.stdout.write(result)


def address(value):
    require(isinstance(value, str) and re.fullmatch(r"0x[0-9a-fA-F]{40}", value), "invalid Ethereum address")
    result = value.lower()
    require(int(result[2:], 16) != 0, "zero address is not a recipient")
    return result


def token_units(value, decimals):
    require(isinstance(value, str) and len(value) <= 340,
            "budget must be a decimal string, never a JSON float")
    require(re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value),
            "budget must be unsigned ordinary decimal notation")
    whole, _, fraction = value.partition(".")
    require(len(fraction) <= decimals, "budget has more fractional digits than the token")
    result = int(whole) * 10 ** decimals + int((fraction + "0" * decimals)[:decimals] or "0")
    require(0 < result <= UINT256_MAX, "budget must be positive and fit uint256")
    return result


def display_units(units, decimals):
    if decimals == 0:
        return str(units)
    whole, fraction = divmod(units, 10 ** decimals)
    return str(whole) + "." + str(fraction).zfill(decimals)


def weight(value):
    require(isinstance(value, str) and re.fullmatch(r"(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,18})?", value),
            "weight must be a nonnegative decimal string with at most 18 whole and 18 fractional digits")
    return Fraction(value)


def validate_metadata(metadata):
    require(isinstance(metadata, dict) and metadata.get("schema") == "rewardsplit-token-v1", "unknown metadata schema")
    require(type(metadata.get("chain_id")) is int and metadata["chain_id"] == 1, "metadata must describe Ethereum mainnet")
    contract = address(metadata.get("address"))
    require(contract in TOKENS.values(), "metadata token must be ZTO or IMD")
    decimals = metadata.get("decimals")
    require(type(decimals) is int and 0 <= decimals <= 255, "invalid token decimals")
    require(isinstance(metadata.get("symbol"), str) and 0 < len(metadata["symbol"]) <= 128, "invalid token symbol")
    require(type(metadata.get("block_number")) is int and metadata["block_number"] >= 0, "invalid metadata block number")
    require(isinstance(metadata.get("block_hash"), str) and re.fullmatch(r"0x[0-9a-f]{64}", metadata["block_hash"]), "invalid block hash")
    return decimals


def allocate(request, metadata):
    decimals = validate_metadata(metadata)
    require(isinstance(request, dict) and set(request) == {"budget", "contributors"},
            "input must contain exactly budget and contributors")
    budget = token_units(request["budget"], decimals)
    rows = request["contributors"]
    require(isinstance(rows, list) and 1 <= len(rows) <= MAX_CONTRIBUTORS,
            "contributors must contain between 1 and 1000 rows")
    parsed = []
    ids, addresses = set(), set()
    for row in rows:
        require(isinstance(row, dict) and {"id", "weight"} <= set(row) <= {"id", "weight", "address"},
                "each contributor needs id and weight, and optionally address")
        identifier = row["id"]
        require(isinstance(identifier, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", identifier),
                "id must be 1-64 ASCII letters, digits, dots, underscores or hyphens")
        require(identifier not in ids, "duplicate contributor id: " + identifier)
        ids.add(identifier)
        recipient = address(row["address"]) if "address" in row else None
        require(recipient is None or recipient not in addresses, "duplicate recipient address")
        if recipient:
            addresses.add(recipient)
        parsed.append((identifier, weight(row["weight"]), recipient))
    total_weight = sum((item[1] for item in parsed), Fraction(0))
    require(total_weight > 0, "at least one weight must be positive")
    # Canonical order makes equal-remainder ties independent of input ordering.
    parsed.sort(key=lambda row: row[0])
    shares = [Fraction(budget) * item[1] / total_weight for item in parsed]
    floors = [share.numerator // share.denominator for share in shares]
    remainders = [share - floor for share, floor in zip(shares, floors)]
    leftover = budget - sum(floors)
    ranked = sorted(range(len(parsed)), key=lambda i: (-remainders[i], parsed[i][0]))
    winners = set(ranked[:leftover])
    allocations = []
    for i, (identifier, proportion, recipient) in enumerate(parsed):
        units = floors[i] + (i in winners)
        allocation = {
            "id": identifier,
            "weight_fraction": str(proportion),
            "units": str(units),
            "amount": display_units(units, decimals),
            "rounding_unit_awarded": i in winners,
        }
        if recipient:
            allocation["address"] = recipient
        allocations.append(allocation)
    assert sum(int(item["units"]) for item in allocations) == budget
    return {
        "schema": "rewardsplit-allocation-v1",
        "purpose": "allocation only; no transaction, balance check, or promise of payment",
        "token": {key: metadata[key] for key in ("chain_id", "address", "symbol", "decimals", "block_number", "block_hash")},
        "budget_units": str(budget),
        "budget_amount": display_units(budget, decimals),
        "method": "largest remainder; equal remainders ordered by ASCII contributor id",
        "rounding_units_distributed": leftover,
        "unallocated_units": "0",
        "all_recipients_supplied": all(item[2] is not None for item in parsed),
        "allocations": allocations,
    }


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Invalid("RPC redirects are refused")


class Rpc:
    def __init__(self, endpoint):
        parts = urllib.parse.urlsplit(endpoint)
        require(parts.scheme in ("http", "https") and bool(parts.hostname)
                and parts.username is None and parts.password is None
                and not parts.fragment and not parts.query, "RPC must be an HTTP(S) URL without credentials, query, or fragment")
        require(parts.scheme == "https" or parts.hostname in ("127.0.0.1", "localhost", "::1"),
                "remote RPC endpoints require HTTPS")
        self.endpoint = endpoint
        self.sequence = 0
        # Explicitly avoid environment proxy discovery and wallet/config files.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def call(self, method, params):
        require(method in {"eth_chainId", "eth_blockNumber", "eth_getBlockByNumber", "eth_call"}, "read-only RPC method required")
        self.sequence += 1
        body = json.dumps({"jsonrpc": "2.0", "id": self.sequence, "method": method, "params": params}).encode()
        request = urllib.request.Request(self.endpoint, data=body, headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
        with self.opener.open(request, timeout=20) as response:
            raw = response.read(MAX_BYTES + 1)
        require(len(raw) <= MAX_BYTES, "RPC response exceeds byte limit")
        result = parse_json(raw)
        require(isinstance(result, dict) and result.get("jsonrpc") == "2.0"
                and type(result.get("id")) is int and result["id"] == self.sequence, "invalid RPC response envelope")
        require("error" not in result and "result" in result, "RPC returned an error or no result")
        return result["result"]


def quantity(value):
    require(isinstance(value, str) and re.fullmatch(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)", value), "invalid RPC quantity")
    return int(value, 16)


def abi_bytes(value):
    require(isinstance(value, str) and re.fullmatch(r"0x(?:[0-9a-fA-F]{2})*", value), "invalid ABI response")
    return bytes.fromhex(value[2:])


def abi_uint(value):
    data = abi_bytes(value)
    require(len(data) == 32, "expected one ABI uint256 word")
    return int.from_bytes(data, "big")


def abi_string(value):
    data = abi_bytes(value)
    if len(data) == 32:
        raw = data.rstrip(b"\0")  # Legacy ERC-20 bytes32 metadata.
    else:
        require(len(data) >= 64 and len(data) % 32 == 0 and int.from_bytes(data[:32], "big") == 32,
                "invalid ABI string offset")
        size = int.from_bytes(data[32:64], "big")
        require(0 < size <= 128 and len(data) == 64 + ((size + 31) // 32) * 32,
                "invalid ABI string length")
        raw = data[64:64 + size]
        require(not any(data[64 + size:]), "invalid ABI string padding")
    try:
        result = raw.decode("utf-8")
    except UnicodeError as exc:
        raise Invalid("token metadata is not UTF-8") from exc
    require(result and len(result) <= 128 and all(c.isprintable() for c in result), "invalid token text metadata")
    return result


def inspect_token(endpoint, token="zto", source=PUBLIC_RPC):
    rpc = Rpc(endpoint)
    require(quantity(rpc.call("eth_chainId", [])) == 1, "RPC is not Ethereum mainnet")
    block = rpc.call("eth_blockNumber", [])
    block_number = quantity(block)
    before = rpc.call("eth_getBlockByNumber", [block, False])
    require(isinstance(before, dict) and quantity(before.get("number")) == block_number, "RPC returned a different block")
    contract = TOKENS[token]

    def call(selector):
        return rpc.call("eth_call", [{"to": contract, "data": selector}, block])

    metadata = {
        "schema": "rewardsplit-token-v1",
        "chain_id": 1,
        "address": contract,
        "symbol": abi_string(call("0x95d89b41")),
        "name": abi_string(call("0x06fdde03")),
        "decimals": abi_uint(call("0x313ce567")),
        "total_supply_units": str(abi_uint(call("0x18160ddd"))),
        "block_number": block_number,
        "block_hash": before.get("hash"),
        "source": source,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "trust": "single RPC observation; not an independent proof or balance check",
    }
    after = rpc.call("eth_getBlockByNumber", [block, False])
    require(isinstance(after, dict) and after.get("hash") == metadata["block_hash"]
            and quantity(after.get("number")) == block_number, "block changed during metadata capture; retry")
    validate_metadata(metadata)
    return metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="offline three-role allocation using captured real ZTO decimals")
    allocate_parser = sub.add_parser("allocate", help="allocate a supplied budget and contributor weights")
    allocate_parser.add_argument("--input", required=True)
    allocate_parser.add_argument("--metadata", default=str(Path(__file__).with_name("zto-mainnet.json")))
    allocate_parser.add_argument("--output")
    inspect_parser = sub.add_parser("inspect", help="capture read-only ZTO or IMD metadata at one Ethereum block")
    inspect_parser.add_argument("--rpc", default=PUBLIC_RPC)
    inspect_parser.add_argument("--source", default=PUBLIC_RPC, help="public provenance URL if a transport relay is used")
    inspect_parser.add_argument("--token", choices=sorted(TOKENS), default="zto")
    inspect_parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            directory = Path(__file__).resolve().parent
            result = allocate(read_json(directory / "example.json"), read_json(directory / "zto-mainnet.json"))
            result["demo"] = "Illustrative task roles, not recipient identities; no addresses or payments."
            write_json(result)
        elif args.command == "allocate":
            write_json(allocate(read_json(args.input), read_json(args.metadata)), args.output)
        else:
            write_json(inspect_token(args.rpc, args.token, args.source), args.output)
    except (Invalid, OSError, urllib.error.URLError, ValueError, OverflowError) as exc:
        # Do not echo endpoint strings: a user's URL could contain sensitive path data.
        message = str(exc) if isinstance(exc, Invalid) else type(exc).__name__
        print("rewardsplit: " + message, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
