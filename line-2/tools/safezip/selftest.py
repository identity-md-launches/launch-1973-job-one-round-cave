#!/usr/bin/env python3
"""Offline functional and adversarial checks, using only disposable workspace data."""
from pathlib import Path
import stat
import struct
import tempfile
import unittest
import warnings
import zipfile

from safezip import process, Rejected


class SafeZipTests(unittest.TestCase):
    def setUp(self):
        scratch = Path('test/scratch')
        scratch.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix='safezip-test-', dir=scratch)
        self.root = Path(self.tmp.name)
        self.archive = self.root / 'input.zip'
        self.output = self.root / 'output'

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, members, compression=zipfile.ZIP_STORED):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(self.archive, 'w', compression=compression) as archive:
                for name, data in members:
                    archive.writestr(name, data)

    def reject(self, members, **limits):
        self.make(members)
        with self.assertRaises((Rejected, zipfile.BadZipFile)):
            process(self.archive, self.output, **limits)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob('.safezip-*')))

    def test_roundtrip(self):
        self.make([('docs/readme.txt', b'hello\n'), ('empty/', b''), ('zero', b'')])
        before = process(self.archive)
        self.assertFalse(self.output.exists())
        result = process(self.archive, self.output)
        self.assertEqual(result['total_bytes'], 6)
        self.assertEqual(before['entries'], result['entries'])
        self.assertEqual((self.output / 'docs/readme.txt').read_bytes(), b'hello\n')
        self.assertTrue((self.output / 'empty').is_dir())
        self.assertEqual(result['entries'][0]['sha256'],
                         '5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03')

    def test_deflate(self):
        self.make([('data', b'abc' * 100)], zipfile.ZIP_DEFLATED)
        self.assertEqual(process(self.archive, self.output)['total_bytes'], 300)

    def test_paths(self):
        for name in ['../escape', '/absolute', 'a/../../escape', 'a\\escape',
                     'C:/drive', 'a//b', './a', 'a/./b', 'a/../b', 'NUL.txt',
                     'a.', 'a ', 'cafe\u0301', 'bad:stream', 'a\x01b', 'a/' * 33 + 'deep']:
            with self.subTest(name=name):
                self.reject([(name, b'x')])

    def test_collisions(self):
        for names in [('a', 'a'), ('A', 'a'), ('a', 'a/b'), ('a/b', 'a'),
                      ('A/b', 'a/c'), ('A/', 'a/b')]:
            with self.subTest(names=names):
                self.reject([(name, b'') for name in names])

    def test_explicit_directory_after_implicit(self):
        self.make([('a/b', b'x'), ('a/', b'')])
        process(self.archive, self.output)
        self.assertEqual((self.output / 'a/b').read_bytes(), b'x')

    def test_symlink_and_special_members(self):
        for mode in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR):
            info = zipfile.ZipInfo('link')
            info.create_system = 3
            info.external_attr = (mode | 0o777) << 16
            self.reject([(info, b'target')])

    def test_byte_and_entry_limits(self):
        self.reject([('big', b'12345')], file_bytes=4)
        self.reject([('a', b'123'), ('b', b'456')], total_bytes=5)
        self.reject([('a', b''), ('b', b'')], entries=1)
        self.make([('big', b'0' * 10000)], zipfile.ZIP_DEFLATED)
        with self.assertRaises(Rejected):
            process(self.archive, self.output, ratio=2)
        with self.assertRaises(Rejected):
            process(self.archive, archive_bytes=1)
        with self.assertRaises(Rejected):
            process(self.archive, entries=0)

    def test_crc_failure_is_atomic(self):
        self.make([('first', b'good'), ('second', b'broken')])
        raw = bytearray(self.archive.read_bytes())
        offset = raw.index(b'broken')
        raw[offset] ^= 1
        self.archive.write_bytes(raw)
        with self.assertRaises(zipfile.BadZipFile):
            process(self.archive, self.output)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob('.safezip-*')))

    def test_corrupt_deflate_cli_cleans_stage(self):
        import subprocess
        self.make([('first', b'good'), ('bad', b'payload' * 30)], zipfile.ZIP_DEFLATED)
        with zipfile.ZipFile(self.archive) as archive:
            info = archive.getinfo('bad')
            start = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
            size = info.compress_size
        raw = bytearray(self.archive.read_bytes())
        raw[start:start + size] = b'\xff' * size
        self.archive.write_bytes(raw)
        result = subprocess.run(['python3', '-B', str(Path(__file__).with_name('safezip.py')),
                                 'extract', str(self.archive), str(self.output)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob('.safezip-*')))

    def test_truncated_archive(self):
        self.archive.write_bytes(b'PK\x03\x04')
        with self.assertRaises(zipfile.BadZipFile):
            process(self.archive, self.output)
        self.assertFalse(self.output.exists())

    def test_output_no_clobber(self):
        self.make([('ok', b'x')])
        self.output.mkdir()
        (self.output / 'keep').write_text('original')
        with self.assertRaises(Rejected):
            process(self.archive, self.output)
        self.assertEqual((self.output / 'keep').read_text(), 'original')

    def test_symlink_paths_refused(self):
        self.make([('ok', b'x')])
        link = self.root / 'alias'
        link.symlink_to('input.zip')
        with self.assertRaises(Rejected):
            process(link)
        link.unlink()
        link.symlink_to('missing-directory', target_is_directory=True)
        with self.assertRaises(Rejected):
            process(self.archive, link / 'output')

    def test_outside_workspace_refused_without_read(self):
        with self.assertRaises(Rejected):
            process('../never-read-this.zip')
        self.make([('ok', b'x')])
        with self.assertRaises(Rejected):
            process(self.archive, '../never-write-this')

    def test_unsupported_compression(self):
        self.make([('ok', b'x')], zipfile.ZIP_BZIP2)
        with self.assertRaises(Rejected):
            process(self.archive)

    def test_encrypted_flag(self):
        self.make([('ok', b'x')])
        raw = bytearray(self.archive.read_bytes())
        central = raw.index(b'PK\x01\x02')
        struct.pack_into('<H', raw, central + 8, 1)
        self.archive.write_bytes(raw)
        with self.assertRaises(Rejected):
            process(self.archive)

    def test_cli(self):
        import subprocess
        self.make([('ok', b'x')])
        script = Path(__file__).with_name('safezip.py')
        result = subprocess.run(['python3', '-B', str(script), 'inspect', str(self.archive)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"content_checked": true', result.stdout)
        result = subprocess.run(['python3', '-B', str(script), 'extract', str(self.archive),
                                 str(self.output), '--file-bytes', '0'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('"ok": false', result.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
