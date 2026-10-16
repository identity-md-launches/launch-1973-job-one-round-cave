#!/usr/bin/env python3
"""Bounded ZIP inspection and staged extraction. Standard library only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import unicodedata
import zlib
import zipfile


class Rejected(ValueError):
    pass


def local_path(value):
    """Confine all user paths to cwd, refusing every existing symlink component."""
    root = Path.cwd().resolve()
    path = Path(os.path.abspath(value))
    try:
        relative = path.relative_to(root)
    except ValueError:
        raise Rejected('path must be inside the current workspace') from None
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise Rejected('symlink in workspace path')
    return path


def member_name(info):
    name = info.orig_filename
    if unicodedata.normalize('NFC', name) != name:
        raise Rejected('member path must use NFC Unicode normalization')
    if '\x00' in name or '\\' in name or name.startswith('/'):
        raise Rejected('unsafe member path: ' + repr(name))
    parts = name[:-1].split('/') if name.endswith('/') else name.split('/')
    if not parts or len(parts) > 32 or len(name.encode('utf-8')) > 1024:
        raise Rejected('member path too long or deep')
    reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{p}{n}' for p in ('COM', 'LPT') for n in range(1, 10)}
    for part in parts:
        if (part in ('', '.', '..') or part.endswith((' ', '.'))
                or re.search(r'[<>:"|?*\x00-\x1f\x7f]', part)
                or part.split('.')[0].upper() in reserved
                or len(part.encode('utf-8')) > 255):
            raise Rejected('unsafe member path: ' + repr(name))
    mode = info.external_attr >> 16
    kind = stat.S_IFMT(mode)
    if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
        raise Rejected('link or special member: ' + repr(name))
    if kind == stat.S_IFDIR and not info.is_dir():
        raise Rejected('directory metadata/name mismatch')
    if kind == stat.S_IFREG and info.is_dir():
        raise Rejected('file metadata/name mismatch')
    if info.flag_bits & 1:
        raise Rejected('encrypted member')
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise Rejected('unsupported compression (only stored and deflate accepted)')
    return '/'.join(parts)


def inventory(archive, limits):
    infos = archive.infolist()
    if len(infos) > limits.entries:
        raise Rejected('entry limit exceeded')
    nodes = {}
    explicit = set()
    total = 0
    entries = []
    for info in infos:
        name = member_name(info)
        key = name.casefold()
        if key in explicit:
            raise Rejected('duplicate or case-colliding member: ' + repr(name))
        explicit.add(key)
        parts = name.split('/')
        for index in range(1, len(parts) + 1):
            prefix = '/'.join(parts[:index])
            directory = index < len(parts) or info.is_dir()
            prior = nodes.get(prefix.casefold())
            if prior and (prior[0] != prefix or prior[1] != directory):
                raise Rejected('file/directory or case collision: ' + repr(prefix))
            nodes[prefix.casefold()] = (prefix, directory)
        if info.file_size > limits.file_bytes:
            raise Rejected('individual file limit exceeded')
        total += info.file_size
        if total > limits.total_bytes:
            raise Rejected('total uncompressed limit exceeded')
        if info.file_size > max(1, info.compress_size) * limits.ratio:
            raise Rejected('compression ratio limit exceeded')
        if info.is_dir() and info.file_size:
            raise Rejected('directory contains data')
        entries.append((info, name))
    return entries, total


def process(archive_path, output=None, *, entries=1000, file_bytes=16*1024*1024,
            total_bytes=64*1024*1024, archive_bytes=32*1024*1024, ratio=200):
    limits = argparse.Namespace(entries=entries, file_bytes=file_bytes,
                                total_bytes=total_bytes, ratio=ratio)
    if min(entries, file_bytes, total_bytes, archive_bytes, ratio) <= 0:
        raise Rejected('all limits must be positive')
    source = local_path(archive_path)
    if not source.is_file() or source.stat().st_size > archive_bytes:
        raise Rejected('archive missing, nonregular, or over archive byte limit')
    target = local_path(output) if output is not None else None
    if target is not None:
        if target.exists():
            raise Rejected('output must not already exist')
        if not target.parent.is_dir():
            raise Rejected('output parent must already exist')
    stage = None
    try:
        with zipfile.ZipFile(source) as archive:
            members, total = inventory(archive, limits)
            if target is not None:
                stage = Path(tempfile.mkdtemp(prefix='.safezip-', dir=target.parent))
            records = []
            actual_total = 0
            for info, name in members:
                record = {'path': name, 'kind': 'directory' if info.is_dir() else 'file',
                          'bytes': info.file_size}
                if info.is_dir():
                    if stage is not None:
                        (stage / name).mkdir(parents=True, exist_ok=True)
                else:
                    digest = hashlib.sha256()
                    count = 0
                    destination = None
                    try:
                        if stage is not None:
                            path = stage / name
                            path.parent.mkdir(parents=True, exist_ok=True)
                            destination = path.open('xb')
                        with archive.open(info) as reader:
                            while True:
                                chunk = reader.read(65536)
                                if not chunk:
                                    break
                                count += len(chunk)
                                actual_total += len(chunk)
                                if count > file_bytes or actual_total > total_bytes:
                                    raise Rejected('actual uncompressed byte limit exceeded')
                                digest.update(chunk)
                                if destination is not None:
                                    destination.write(chunk)
                    finally:
                        if destination is not None:
                            destination.close()
                    if count != info.file_size:
                        raise Rejected('declared and actual size differ')
                    record['sha256'] = digest.hexdigest()
                records.append(record)
            if target is not None:
                # A cooperative workspace is required; no concurrent path mutations.
                if target.exists() or target.is_symlink():
                    raise Rejected('output appeared during extraction')
                stage.rename(target)
                stage = None
            return {'ok': True, 'mode': 'extract' if target else 'inspect',
                    'entries': records, 'total_bytes': total,
                    'content_checked': True}
    finally:
        if stage is not None:
            shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('inspect', 'extract'))
    parser.add_argument('archive')
    parser.add_argument('output', nargs='?')
    for flag, default in [('entries', 1000), ('file-bytes', 16*1024*1024),
                          ('total-bytes', 64*1024*1024), ('archive-bytes', 32*1024*1024),
                          ('ratio', 200)]:
        parser.add_argument('--' + flag, type=int, default=default)
    args = parser.parse_args()
    if (args.command == 'extract') != (args.output is not None):
        parser.error('extract requires an output directory; inspect takes no output')
    try:
        result = process(args.archive, args.output, entries=args.entries,
                         file_bytes=args.file_bytes, total_bytes=args.total_bytes,
                         archive_bytes=args.archive_bytes, ratio=args.ratio)
    except (ValueError, OSError, zipfile.BadZipFile, NotImplementedError, RuntimeError, EOFError, zlib.error) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=True))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
