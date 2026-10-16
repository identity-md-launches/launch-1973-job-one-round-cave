#!/usr/bin/env python3
"""Behavioral regression tests. No network, wallet or third-party dependencies."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

import apidelta as api


def document(request=None, response=None):
    op = {'responses': {'200': {'description': 'OK', 'content': {
        'application/json': {'schema': response or {'type': 'string'}}}}}}
    if request is not None:
        op['requestBody'] = {'content': {'application/json': {'schema': request}}}
    return {'openapi': '3.1.0', 'info': {'title': 'Test', 'version': '1'},
            'paths': {'/items': {'post': op}}}


def codes(report, severity=None):
    return {f['code'] for f in report['findings']
            if severity is None or f['severity'] == severity}


class Changes(unittest.TestCase):
    def compare_schema(self, old, new, direction='request'):
        if direction == 'request':
            return api.compare(document(request=old), document(request=new))
        return api.compare(document(response=old), document(response=new))

    def test_real_baseline_unchanged(self):
        original, _ = api.load(Path(__file__).with_name('imd-openapi.json'))
        report = api.compare(original, copy.deepcopy(original))
        self.assertEqual(report['findings'], [])
        self.assertEqual(report['operations_compared'], 5)

    def test_demo_catches_two_breaks(self):
        report = api.demo()
        self.assertEqual(report['counts'], {'breaking': 2, 'review': 0, 'info': 0})
        self.assertIn('request_property_required', codes(report))
        self.assertIn('operation_removed', codes(report))

    def test_operation_removed(self):
        old, new = document(), document()
        new['paths'] = {}
        self.assertEqual(codes(api.compare(old, new)), {'operation_removed'})

    def test_operation_added_is_info(self):
        old, new = document(), document()
        old['paths'] = {}
        self.assertEqual(api.compare(old, new)['status'], 'no_detected_breakage')

    def test_request_enum_shrink_breaks(self):
        self.assertIn('schema_enum_incompatible', codes(self.compare_schema(
            {'enum': ['a', 'b']}, {'enum': ['a']}), 'breaking'))

    def test_request_enum_expand_safe(self):
        self.assertEqual(self.compare_schema({'enum': ['a']}, {'enum': ['a', 'b']})['findings'], [])

    def test_response_enum_expand_breaks(self):
        self.assertIn('schema_enum_incompatible', codes(self.compare_schema(
            {'enum': ['a']}, {'enum': ['a', 'b']}, 'response'), 'breaking'))

    def test_response_enum_shrink_safe(self):
        self.assertEqual(self.compare_schema({'enum': ['a', 'b']}, {'enum': ['a']}, 'response')['findings'], [])

    def test_enum_literals_not_annotation_filtered(self):
        self.assertIn('schema_enum_incompatible', codes(self.compare_schema(
            {'enum': [{'description': 'old'}]}, {'enum': [{'description': 'new'}]})))

    def test_bool_and_integer_enum_distinct(self):
        self.assertIn('schema_enum_incompatible', codes(self.compare_schema({'enum': [True]}, {'enum': [1]})))

    def test_integer_number_variance(self):
        self.assertEqual(self.compare_schema({'type': 'integer'}, {'type': 'number'})['findings'], [])
        self.assertIn('schema_type_incompatible', codes(self.compare_schema({'type': 'number'}, {'type': 'integer'})))
        self.assertIn('schema_type_incompatible', codes(self.compare_schema(
            {'type': 'integer'}, {'type': 'number'}, 'response')))

    def test_nullability(self):
        self.assertIn('schema_type_incompatible', codes(self.compare_schema(
            {'type': ['string', 'null']}, {'type': 'string'})))
        self.assertIn('schema_type_incompatible', codes(self.compare_schema(
            {'type': 'string'}, {'type': ['string', 'null']}, 'response')))

    def test_request_required_added(self):
        self.assertIn('request_property_required', codes(self.compare_schema(
            {'type': 'object'}, {'type': 'object', 'required': ['name']})))

    def test_response_required_removed(self):
        self.assertIn('response_property_not_guaranteed', codes(self.compare_schema(
            {'required': ['name']}, {}, 'response')))

    def test_description_named_property_not_ignored(self):
        self.assertIn('schema_type_incompatible', codes(self.compare_schema(
            {'properties': {'description': {'type': 'string'}}},
            {'properties': {'description': {'type': 'number'}}})))

    def test_array_items_recurse(self):
        self.assertIn('schema_type_incompatible', codes(self.compare_schema(
            {'type': 'array', 'items': {'type': 'string'}},
            {'type': 'array', 'items': {'type': 'integer'}})))

    def test_closed_request_property_removed(self):
        self.assertIn('property_removed', codes(self.compare_schema(
            {'properties': {'x': {'type': 'string'}}, 'additionalProperties': False},
            {'additionalProperties': False}), 'breaking'))

    def test_closed_response_property_added(self):
        self.assertIn('response_property_added_to_closed_object', codes(self.compare_schema(
            {'additionalProperties': False},
            {'additionalProperties': False, 'properties': {'x': {'type': 'string'}}}, 'response')))

    def test_unknown_constraint_needs_review(self):
        self.assertEqual(self.compare_schema({'minLength': 1}, {'minLength': 2})['status'], 'review_required')

    def test_composition_needs_review(self):
        self.assertEqual(self.compare_schema({'oneOf': [{'type': 'string'}]},
                                            {'oneOf': [{'type': 'integer'}]})['status'], 'review_required')

    def test_boolean_schema_needs_review(self):
        # Use schema API directly because document helper supplies a default for false.
        analyzer = api.Analyzer(document(), document())
        analyzer.schema(True, False, '/schema', 'request')
        self.assertEqual(analyzer.findings[0]['severity'], 'review')

    def test_parameter_inheritance_and_override(self):
        old, new = document(), document()
        for doc in (old, new):
            doc['paths']['/items']['parameters'] = [{'name': 'q', 'in': 'query', 'required': True}]
            doc['paths']['/items']['post']['parameters'] = [{'name': 'q', 'in': 'query', 'required': False}]
        del new['paths']['/items']['post']['parameters']
        self.assertIn('parameter_became_required', codes(api.compare(old, new), 'breaking'))

    def test_new_required_parameter(self):
        old, new = document(), document()
        new['paths']['/items']['post']['parameters'] = [{'name': 'q', 'in': 'query', 'required': True}]
        self.assertIn('parameter_added', codes(api.compare(old, new), 'breaking'))

    def test_header_case_is_insensitive(self):
        old, new = document(), document()
        old['paths']['/items']['post']['parameters'] = [{'name': 'Accept', 'in': 'header'}]
        new['paths']['/items']['post']['parameters'] = [{'name': 'accept', 'in': 'header'}]
        self.assertNotIn('parameter_added', codes(api.compare(old, new)))

    def test_effective_security(self):
        old, new = document(), document()
        new['security'] = [{'publicSchemeName': []}]
        self.assertIn('security_changed', codes(api.compare(old, new)))
        for doc in (old, new):
            doc['paths']['/items']['post']['security'] = []
        self.assertNotIn('security_changed', codes(api.compare(old, new)))

    def test_ref_target_change_under_same_ref(self):
        old, new = document(response={'$ref': '#/components/schemas/Thing'}), document(response={'$ref': '#/components/schemas/Thing'})
        old['components'] = {'schemas': {'Thing': {'type': 'string'}}}
        new['components'] = {'schemas': {'Thing': {'type': 'number'}}}
        self.assertIn('schema_type_incompatible', codes(api.compare(old, new), 'breaking'))

    def test_recursive_refs_terminate(self):
        old = document(response={'$ref': '#/components/schemas/Node'})
        old['components'] = {'schemas': {'Node': {'type': 'object', 'properties': {
            'child': {'$ref': '#/components/schemas/Node'}, 'value': {'type': 'string'}}}}}
        new = copy.deepcopy(old)
        new['components']['schemas']['Node']['properties']['value'] = {'type': 'number'}
        self.assertIn('schema_type_incompatible', codes(api.compare(old, new)))
        self.assertLess(len(api.compare(old, new)['findings']), 10)

    def test_ref_pointer_escaping(self):
        old = document(response={'$ref': '#/components/schemas/a~1b~0c'})
        old['components'] = {'schemas': {'a/b~c': {'type': 'string'}}}
        self.assertEqual(api.compare(old, copy.deepcopy(old))['findings'], [])

    def test_external_ref_never_fetched(self):
        old = document(response={'$ref': 'https://api.imd.fun/openapi.json'})
        with self.assertRaisesRegex(api.Invalid, 'only local'):
            api.compare(old, document())

    def test_missing_ref_rejected(self):
        with self.assertRaisesRegex(api.Invalid, 'unresolved'):
            api.compare(document(response={'$ref': '#/missing'}), document())

    def test_alias_cycle_rejected(self):
        old = document(response={'$ref': '#/components/schemas/A'})
        old['components'] = {'schemas': {'A': {'$ref': '#/components/schemas/B'}, 'B': {'$ref': '#/components/schemas/A'}}}
        with self.assertRaisesRegex(api.Invalid, 'alias cycle'):
            api.compare(old, document())

    def test_semantic_ref_siblings_rejected(self):
        old = document(response={'$ref': '#/components/schemas/A', 'maxLength': 4})
        old['components'] = {'schemas': {'A': {'type': 'string'}}}
        with self.assertRaisesRegex(api.Invalid, 'siblings'):
            api.compare(old, document())

    def test_path_refs_rejected(self):
        old = document()
        old['paths']['/items']['$ref'] = '#/something'
        with self.assertRaises(api.Invalid):
            api.compare(old, document())

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(api.Invalid):
            json.loads('{"paths":{},"paths":{}}', object_pairs_hook=api.pairs)

    def test_output_locations_escape(self):
        old, new = document(), document()
        old['paths']['/a~b/c'] = old['paths'].pop('/items')
        report = api.compare(old, new)
        self.assertTrue(any('/~1a~0b~1c/' in f['location'] for f in report['findings']))

    def test_limits(self):
        old = document()
        value = old
        for _ in range(api.MAX_DEPTH + 1):
            value['child'] = {}
            value = value['child']
        with self.assertRaisesRegex(api.Invalid, 'structural limits'):
            api.validate(old)

    def test_deterministic_object_order(self):
        old = document(request={'type': 'string'})
        new = document(request={'type': 'number'})
        reordered = json.loads(json.dumps(new, sort_keys=True))
        self.assertEqual(api.compare(old, new), api.compare(old, reordered))

    def test_cli_demo_exit_zero(self):
        result = subprocess.run([sys.executable, '-B', str(Path(__file__).with_name('apidelta.py')), 'demo'],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['counts']['breaking'], 2)

    def test_cli_exit_codes_and_output_refusal(self):
        # Scratch files are local to the workspace and never become dependencies.
        import tempfile
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as scratch:
            root = Path(scratch)
            old = root / 'old.json'
            new = root / 'new.json'
            output = root / 'report.json'
            old.write_text(json.dumps(document(request={'type': 'string'})))
            script = str(Path(__file__).with_name('apidelta.py'))
            def run(*extra):
                return subprocess.run([sys.executable, '-B', script, 'compare', str(old), str(new), *extra],
                                      capture_output=True, text=True, timeout=10)
            new.write_bytes(old.read_bytes())
            self.assertEqual(run().returncode, 0)
            new.write_text(json.dumps(document(request={'type': 'number'})))
            self.assertEqual(run('--output', str(output)).returncode, 1)
            saved = output.read_bytes()
            self.assertEqual(json.loads(saved)['counts']['breaking'], 1)
            self.assertEqual(run('--output', str(output)).returncode, 2)
            self.assertEqual(output.read_bytes(), saved)
            new.write_text(json.dumps(document(request={'type': 'string', 'pattern': 'abc'})))
            self.assertEqual(run().returncode, 3)
            new.write_text('{"paths":{},"paths":{}}')
            self.assertEqual(run().returncode, 2)

    def test_workspace_escape_rejected(self):
        with self.assertRaisesRegex(api.Invalid, 'inside'):
            api.path_in_workspace(Path.cwd().parent / 'outside.json')

    def test_schema_annotation_is_reviewed(self):
        self.assertEqual(self.compare_schema({'type': 'string', 'description': 'old'},
                                            {'type': 'string', 'description': 'new'})['status'], 'review_required')

    def test_request_media_type_removed(self):
        old, new = document(request={'type': 'string'}), document()
        self.assertIn('media_type_removed', codes(api.compare(old, new), 'breaking'))

    def test_response_status_added(self):
        old, new = document(), document()
        new['paths']['/items']['post']['responses']['202'] = {'description': 'Pending'}
        self.assertEqual(api.compare(old, new)['status'], 'review_required')

    def test_unused_component_change_is_reviewed(self):
        old, new = document(), document()
        old['components'] = {'schemas': {'Unused': {'type': 'string'}}}
        new['components'] = {'schemas': {'Unused': {'type': 'number'}}}
        self.assertEqual(api.compare(old, new)['status'], 'review_required')


if __name__ == '__main__':
    unittest.main()
