"""Offline integration tests; all disposable files live in test/scratch."""
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

import api_bundle as bundle


class BundleTests(unittest.TestCase):
    def setUp(self):
        scratch = Path('test/scratch')
        scratch.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.root = Path(self.tmp.name)
        self.doc = {'openapi': '3.1.0', 'paths': {'/items': {'get': {
            'responses': {'200': {'description': 'OK'}}}}}}

    def tearDown(self):
        self.tmp.cleanup()

    def archive(self, name, doc=None, extra=(), compression=zipfile.ZIP_STORED):
        path = self.root / name
        with zipfile.ZipFile(path, 'w', compression=compression) as output:
            output.writestr('openapi.json', json.dumps(self.doc if doc is None else doc))
            for filename, data in extra:
                output.writestr(filename, data)
        return path

    def test_unchanged_with_inert_executable(self):
        a = self.archive('a.zip', extra=[('script.py', 'raise RuntimeError("NEVER EXECUTE")')])
        before = sorted(p.name for p in self.root.iterdir())
        report = bundle.compare(a, a)
        self.assertEqual(report['status'], 'no_detected_breakage')
        self.assertEqual(len(report['bundle_inputs']['old']['checked_files']), 2)
        self.assertEqual(before, sorted(p.name for p in self.root.iterdir()))

    def test_break_and_cli_exit(self):
        a = self.archive('a.zip')
        b = self.archive('b.zip', {'openapi': '3.1.0', 'paths': {}})
        self.assertEqual(bundle.compare(a, b)['counts']['breaking'], 1)
        result = subprocess.run([sys.executable, '-B', str(Path(bundle.__file__)), str(a), str(b)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'breaking')

    def test_review_exit(self):
        a = self.archive('a.zip')
        changed = copy.deepcopy(self.doc)
        changed['info'] = {'title': 'changed', 'version': '2'}
        b = self.archive('b.zip', changed)
        result = subprocess.run([sys.executable, '-B', str(Path(bundle.__file__)), str(a), str(b)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 3)

    def test_zip_traversal_refused_even_when_unselected(self):
        a = self.archive('a.zip', extra=[('../escape', b'bad')])
        with self.assertRaises(ValueError):
            bundle.read_bundle(a)

    def test_crc_refused_even_when_unselected(self):
        a = self.archive('a.zip', extra=[('other', b'corrupt-me')])
        raw = a.read_bytes().replace(b'corrupt-me', b'CORRUPT-ME')
        a.write_bytes(raw)
        with self.assertRaises(zipfile.BadZipFile):
            bundle.read_bundle(a)

    def test_duplicate_and_case_collision_refused(self):
        a = self.archive('a.zip', extra=[('OPENAPI.JSON', b'{}')])
        with self.assertRaises(ValueError):
            bundle.read_bundle(a)

    def test_ratio_limit(self):
        a = self.archive('a.zip', extra=[('bomb', b'0'*100000)], compression=zipfile.ZIP_DEFLATED)
        with self.assertRaisesRegex(ValueError, 'ratio'):
            bundle.read_bundle(a)

    def test_json_duplicate_and_size_limits(self):
        for data in [b'{"openapi":"3.1.0","paths":{},"paths":{}}',
                     b' ' * (bundle.apidelta.MAX_BYTES + 1)]:
            a = self.root / 'invalid.zip'
            with zipfile.ZipFile(a, 'w') as output:
                output.writestr('openapi.json', data)
            with self.assertRaises(ValueError):
                bundle.read_bundle(a)

    def test_missing_member_and_symlink(self):
        a = self.archive('a.zip')
        with self.assertRaises(ValueError):
            bundle.read_bundle(a, 'absent.json')
        link = self.root / 'alias.zip'
        link.symlink_to('a.zip')
        with self.assertRaises(ValueError):
            bundle.read_bundle(link)

    def test_real_imd_capture(self):
        # Included public data is copied here, so no line directory is required.
        baseline = json.loads(Path(__file__).with_name('imd-openapi.json').read_bytes())
        a = self.archive('real.zip', baseline)
        report = bundle.compare(a, a)
        self.assertEqual(report['operations_compared'], 5)
        self.assertEqual(report['findings'], [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
