#!/usr/bin/env python3
"""Compare OpenAPI JSON inside ZIP snapshots without extracting any member."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile
import zlib

from vendor import apidelta, safezip

MAX_ARCHIVE = 32 * 1024 * 1024


def read_bundle(path, member='openapi.json'):
    # Snapshot once: validation and comparison see the same bytes even if the
    # source changes later. No archive pathname is ever used as an output path.
    path = safezip.local_path(path)
    if not path.is_file():
        raise ValueError('archive must be an ordinary workspace file')
    with path.open('rb') as source:
        raw = source.read(MAX_ARCHIVE + 1)
    if len(raw) > MAX_ARCHIVE:
        raise ValueError('archive exceeds 32 MiB')
    limits = argparse.Namespace(entries=1000, file_bytes=16*1024*1024,
                                total_bytes=64*1024*1024, ratio=200)
    selected = None
    inventory = []
    actual_total = 0
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries, _ = safezip.inventory(archive, limits)
        for info, name in entries:
            if info.is_dir():
                continue
            if name == member and info.file_size > apidelta.MAX_BYTES:
                raise ValueError('selected description exceeds 1 MiB')
            digest = hashlib.sha256()
            count = 0
            payload = bytearray() if name == member else None
            with archive.open(info) as stream:
                while True:
                    chunk = stream.read(65536)
                    if not chunk:
                        break
                    count += len(chunk)
                    actual_total += len(chunk)
                    if count > limits.file_bytes or actual_total > limits.total_bytes:
                        raise ValueError('streamed ZIP resource limit exceeded')
                    digest.update(chunk)
                    if payload is not None:
                        if count > apidelta.MAX_BYTES:
                            raise ValueError('selected description exceeds 1 MiB')
                        payload.extend(chunk)
            if count != info.file_size:
                raise ValueError('declared and actual member size differ')
            inventory.append({'path': name, 'bytes': count, 'sha256': digest.hexdigest()})
            if payload is not None:
                selected = bytes(payload)
    if selected is None:
        raise ValueError('selected description is missing or is a directory')
    obj = json.loads(selected, object_pairs_hook=apidelta.pairs,
                     parse_constant=lambda _: (_ for _ in ()).throw(ValueError('non-finite JSON')))
    apidelta.validate(obj)
    return obj, {'archive_sha256': hashlib.sha256(raw).hexdigest(),
                 'member': member, 'member_sha256': hashlib.sha256(selected).hexdigest(),
                 'checked_files': inventory, 'all_payloads_crc_checked': True}


def compare(old, new, member='openapi.json'):
    a, before = read_bundle(old, member)
    b, after = read_bundle(new, member)
    report = apidelta.compare(a, b)
    report['bundle_inputs'] = {'old': before, 'new': after}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('old', help='old workspace ZIP')
    parser.add_argument('new', help='new workspace ZIP')
    parser.add_argument('--member', default='openapi.json', help='exact member name in both ZIPs')
    args = parser.parse_args()
    try:
        report = compare(args.old, args.new, args.member)
        print(json.dumps(report, indent=2, allow_nan=False))
        return {'breaking': 1, 'review_required': 3, 'no_detected_breakage': 0}[report['status']]
    except (ValueError, OSError, RuntimeError, EOFError, zipfile.BadZipFile,
            NotImplementedError, zlib.error, RecursionError, TypeError, KeyError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=True))
        return 2


if __name__ == '__main__':
    sys.exit(main())
