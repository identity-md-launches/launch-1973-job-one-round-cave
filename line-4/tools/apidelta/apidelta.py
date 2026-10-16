#!/usr/bin/env python3
"""Conservative, offline OpenAPI change analysis. Python 3.9+, stdlib only."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

MAX_BYTES = 1024 * 1024
MAX_NODES = 50000
MAX_DEPTH = 80
MAX_STEPS = 20000
MAX_FINDINGS = 2000
METHODS = frozenset(('get', 'put', 'post', 'delete', 'options', 'head', 'patch', 'trace'))
ANNOTATIONS = frozenset(('title', 'description', 'summary', 'example', 'examples',
                         'externalDocs', '$comment'))
SCHEMA_HANDLED = frozenset(('type', 'nullable', 'enum', 'required', 'properties',
                            'items', 'additionalProperties')) | ANNOTATIONS


class Invalid(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise Invalid(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False)


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def path_in_workspace(value):
    path = Path(value).resolve()
    require(path.is_relative_to(Path.cwd().resolve()), 'path must resolve inside the current workspace')
    return path


def load(value):
    with path_in_workspace(value).open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, 'description exceeds 1 MiB limit')
    try:
        obj = json.loads(raw, object_pairs_hook=pairs,
                         parse_constant=lambda x: (_ for _ in ()).throw(Invalid('non-finite JSON')))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise Invalid('invalid or excessively nested JSON') from exc
    validate(obj)
    return obj, hashlib.sha256(raw).hexdigest()


def validate(obj):
    require(isinstance(obj, dict), 'OpenAPI description must be an object')
    version = obj.get('openapi')
    require(isinstance(version, str) and re.fullmatch(r'3\.(?:0|1)\.[0-9]+', version),
            'only OpenAPI 3.0.x and 3.1.x JSON are supported')
    require(isinstance(obj.get('paths'), dict), 'OpenAPI paths must be an object')
    count = 0
    stack = [(obj, 0)]
    while stack:
        value, depth = stack.pop()
        count += 1
        require(count <= MAX_NODES and depth <= MAX_DEPTH, 'description exceeds structural limits')
        if isinstance(value, dict):
            require(all(isinstance(k, str) for k in value), 'object keys must be strings')
            stack.extend((v, depth + 1) for v in value.values())
        elif isinstance(value, list):
            stack.extend((v, depth + 1) for v in value)
    for name, item in obj['paths'].items():
        require(name.startswith('/') and isinstance(item, dict), 'invalid path item')
        # Path-item references have contextual merge semantics; do not silently omit them.
        require('$ref' not in item, 'path-item $ref is unsupported; inline the path item')


def pointer_token(value):
    return value.replace('~', '~0').replace('/', '~1')


def pointer(base, name):
    return base + '/' + pointer_token(str(name))


class Document:
    def __init__(self, obj):
        self.obj = obj

    def resolve(self, value):
        seen = set()
        while isinstance(value, dict) and '$ref' in value:
            ref = value['$ref']
            require(isinstance(ref, str) and ref.startswith('#/'),
                    'only local JSON-pointer references are supported; no reference is fetched')
            require(ref not in seen, 'reference alias cycle: ' + ref)
            seen.add(ref)
            siblings = set(value) - {'$ref'} - ANNOTATIONS
            require(not siblings, '$ref with semantic siblings is unsupported: ' + ref)
            target = self.obj
            for token in ref[2:].split('/'):
                require(not re.search(r'~(?:[^01]|$)', token), 'invalid reference escape')
                token = token.replace('~1', '/').replace('~0', '~')
                require(isinstance(target, dict) and token in target, 'unresolved reference: ' + ref)
                target = target[token]
            value = target
        return value


class Analyzer:
    def __init__(self, old, new):
        validate(old)
        validate(new)
        self.old, self.new = Document(old), Document(new)
        self.findings = []
        self.steps = 0
        self.active = set()

    def emit(self, severity, code, location, message):
        require(len(self.findings) < MAX_FINDINGS, 'finding limit exceeded; compare a smaller description')
        self.findings.append(dict(severity=severity, code=code, location=location, message=message))

    def changed(self, old, new, location, code, message, severity='review'):
        if canonical(old) != canonical(new):
            self.emit(severity, code, location, message)

    def schema(self, old, new, loc, direction):
        self.steps += 1
        require(self.steps <= MAX_STEPS, 'schema comparison limit exceeded')
        old, new = self.old.resolve(old), self.new.resolve(new)
        require(isinstance(old, (dict, bool)) and isinstance(new, (dict, bool)), 'schema must be an object or boolean')
        if canonical(old) == canonical(new):
            # References can retain their spelling while their target changes: walk below.
            if '$ref' not in canonical(old):
                return
        if type(old) is bool or type(new) is bool:
            self.changed(old, new, loc, 'boolean_schema_changed', 'Boolean schema changed; review accepted values.')
            return
        pair = (id(old), id(new), direction)
        if pair in self.active:
            return
        self.active.add(pair)
        try:
            self._schema(old, new, loc, direction)
        finally:
            self.active.remove(pair)

    def _schema(self, old, new, loc, direction):
        request = direction == 'request'
        for key in sorted((old.keys() | new.keys()) & ANNOTATIONS):
            self.changed(old.get(key), new.get(key), pointer(loc, key),
                         'schema_annotation_changed', 'Schema annotation changed; check whether client generation relies on it.')
        def types(schema):
            value = schema.get('type')
            if value is None:
                return None
            items = [value] if isinstance(value, str) else value
            require(isinstance(items, list) and items and
                    all(t in ('null', 'boolean', 'object', 'array', 'number', 'integer', 'string') for t in items),
                    'invalid schema type')
            result = set(items)
            if schema.get('nullable') is True:
                result.add('null')
            if 'number' in result:
                result.add('integer')
            return result
        ot, nt = types(old), types(new)
        unsafe = ((ot is None and nt is not None) or
                  (ot is not None and nt is not None and not ot <= nt)) if request else (
                  (nt is None and ot is not None) or
                  (ot is not None and nt is not None and not nt <= ot))
        if unsafe:
            self.emit('breaking', 'schema_type_incompatible', loc + '/type',
                      'Request accepts fewer types.' if request else 'Response can produce types old clients did not expect.')
        def enum(schema):
            if 'enum' not in schema:
                return None
            require(isinstance(schema['enum'], list) and schema['enum'], 'enum must be a nonempty array')
            return {canonical(v) for v in schema['enum']}
        oe, ne = enum(old), enum(new)
        unsafe = ((oe is None and ne is not None) or
                  (oe is not None and ne is not None and not oe <= ne)) if request else (
                  (ne is None and oe is not None) or
                  (oe is not None and ne is not None and not ne <= oe))
        if unsafe:
            self.emit('breaking', 'schema_enum_incompatible', loc + '/enum',
                      'Request enum excludes formerly allowed values.' if request else 'Response enum can contain formerly excluded values.')
        def required(schema):
            result = schema.get('required', [])
            require(isinstance(result, list) and all(isinstance(v, str) for v in result), 'required must be a string array')
            return set(result)
        ore, nre = required(old), required(new)
        for name in sorted((nre - ore) if request else (ore - nre)):
            self.emit('breaking', 'request_property_required' if request else 'response_property_not_guaranteed',
                      pointer(loc + '/required', name),
                      'New request property is mandatory.' if request else 'Old required response property is no longer guaranteed.')
        op, np = old.get('properties', {}), new.get('properties', {})
        require(isinstance(op, dict) and isinstance(np, dict), 'properties must be an object')
        for name in sorted(op.keys() & np.keys()):
            self.schema(op[name], np[name], pointer(loc + '/properties', name), direction)
        for name in sorted(op.keys() - np.keys()):
            severity = 'breaking' if request and new.get('additionalProperties') is False else 'review'
            self.emit(severity, 'property_removed', pointer(loc + '/properties', name),
                      'Property is no longer described; check how existing clients use it.')
        for name in sorted(np.keys() - op.keys()):
            if not request and old.get('additionalProperties') is False:
                self.emit('breaking', 'response_property_added_to_closed_object', pointer(loc + '/properties', name),
                          'Old response schema forbids this new property.')
        oa, na = old.get('additionalProperties', True), new.get('additionalProperties', True)
        if canonical(oa) != canonical(na):
            if (request and na is False and oa is not False) or (not request and oa is False and na is not False):
                self.emit('breaking', 'additional_properties_incompatible', loc + '/additionalProperties',
                          'Additional-property policy changed incompatibly.')
            else:
                self.emit('review', 'additional_properties_changed', loc + '/additionalProperties',
                          'Additional-property schema changed; review constraints.')
        if 'items' in old or 'items' in new:
            self.schema(old.get('items', {}), new.get('items', {}), loc + '/items', direction)
        for key in sorted((old.keys() | new.keys()) - SCHEMA_HANDLED):
            self.changed(old.get(key), new.get(key), pointer(loc, key), 'schema_constraint_changed',
                         'Constraint changed; this rule needs human review.')

    def parameters(self, doc, path_item, operation):
        result = {}
        for layer in (path_item, operation):
            raw = layer.get('parameters', [])
            require(isinstance(raw, list), 'parameters must be an array')
            seen = set()
            for entry in raw:
                item = doc.resolve(entry)
                require(isinstance(item, dict) and isinstance(item.get('name'), str) and
                        item.get('in') in ('query', 'header', 'path', 'cookie'), 'invalid parameter')
                name = item['name'].lower() if item['in'] == 'header' else item['name']
                key = (item['in'], name)
                require(key not in seen, 'duplicate parameter within a layer')
                seen.add(key)
                result[key] = item
        return result

    def content(self, old, new, loc, direction):
        require(isinstance(old, dict) and isinstance(new, dict), 'content must be an object')
        for media in sorted(old.keys() - new.keys()):
            self.emit('breaking' if direction == 'request' else 'review', 'media_type_removed', pointer(loc, media),
                      'Previously described media type was removed.')
        for media in sorted(new.keys() - old.keys()):
            self.emit('info' if direction == 'request' else 'review', 'media_type_added', pointer(loc, media),
                      'New media type is described.')
        for media in sorted(old.keys() & new.keys()):
            a, b = old[media], new[media]
            require(isinstance(a, dict) and isinstance(b, dict), 'media type must be an object')
            self.schema(a.get('schema', {}), b.get('schema', {}), pointer(loc, media) + '/schema', direction)
            self.changed({k: v for k, v in a.items() if k != 'schema'},
                         {k: v for k, v in b.items() if k != 'schema'}, pointer(loc, media),
                         'media_metadata_changed', 'Media encoding or other metadata changed.')

    def operation(self, path, method, old_item, new_item):
        old, new = old_item[method], new_item[method]
        require(isinstance(old, dict) and isinstance(new, dict), 'operation must be an object')
        loc = pointer('/paths', path) + '/' + method
        op = self.parameters(self.old, old_item, old)
        np = self.parameters(self.new, new_item, new)
        for key in sorted(op.keys() | np.keys()):
            ploc = pointer(loc + '/parameters', key[0] + ':' + key[1])
            if key not in np:
                self.emit('review', 'parameter_removed', ploc, 'Parameter removed; old callers may still send it.')
            elif key not in op:
                required = np[key].get('required') is True or key[0] == 'path'
                self.emit('breaking' if required else 'info', 'parameter_added', ploc,
                          'Required parameter added.' if required else 'Optional parameter added.')
            else:
                a, b = op[key], np[key]
                if a.get('required') is not True and b.get('required') is True:
                    self.emit('breaking', 'parameter_became_required', ploc, 'Existing callers may omit this now-required parameter.')
                self.schema(a.get('schema', {}), b.get('schema', {}), ploc + '/schema', 'request')
                self.changed({k: v for k, v in a.items() if k not in ('schema', 'required')},
                             {k: v for k, v in b.items() if k not in ('schema', 'required')}, ploc,
                             'parameter_encoding_changed', 'Parameter encoding or other metadata changed.')
        a = self.old.resolve(old.get('requestBody', {}))
        b = self.new.resolve(new.get('requestBody', {}))
        require(isinstance(a, dict) and isinstance(b, dict), 'requestBody must be an object')
        if a.get('required') is not True and b.get('required') is True:
            self.emit('breaking', 'request_body_became_required', loc + '/requestBody', 'Existing callers may omit the now-required request body.')
        self.content(a.get('content', {}), b.get('content', {}), loc + '/requestBody/content', 'request')
        self.changed({k: v for k, v in a.items() if k not in ('content', 'required')},
                     {k: v for k, v in b.items() if k not in ('content', 'required')}, loc + '/requestBody',
                     'request_body_metadata_changed', 'Request body metadata changed.')
        ores, nres = old.get('responses', {}), new.get('responses', {})
        require(isinstance(ores, dict) and isinstance(nres, dict), 'responses must be an object')
        for status in sorted(ores.keys() | nres.keys()):
            rloc = pointer(loc + '/responses', status)
            if status not in nres or status not in ores:
                self.emit('review', 'response_status_changed', rloc,
                          'Response status was added or removed; review client control flow.')
            else:
                a, b = self.old.resolve(ores[status]), self.new.resolve(nres[status])
                require(isinstance(a, dict) and isinstance(b, dict), 'response must be an object')
                self.content(a.get('content', {}), b.get('content', {}), rloc + '/content', 'response')
                self.changed({k: v for k, v in a.items() if k != 'content'},
                             {k: v for k, v in b.items() if k != 'content'}, rloc,
                             'response_metadata_changed', 'Response headers, links or other metadata changed.')
        # Resolve effective inherited policies so global changes cannot hide behind unchanged operations.
        for key in ('security', 'servers'):
            a = old.get(key, old_item.get(key, self.old.obj.get(key, [])))
            b = new.get(key, new_item.get(key, self.new.obj.get(key, [])))
            self.changed(a, b, loc + '/' + key, key + '_changed', 'Effective ' + key + ' policy changed.')
        handled = {'parameters', 'requestBody', 'responses', 'security', 'servers'}
        self.changed({k: v for k, v in old.items() if k not in handled},
                     {k: v for k, v in new.items() if k not in handled}, loc,
                     'operation_metadata_changed', 'Operation identifier, extension or other metadata changed.')

    def run(self):
        old, new = self.old.obj, self.new.obj
        old_paths, new_paths = old['paths'], new['paths']
        compared = 0
        for path in sorted(old_paths.keys() | new_paths.keys()):
            a, b = old_paths.get(path, {}), new_paths.get(path, {})
            for method in sorted((a.keys() | b.keys()) & METHODS):
                loc = pointer('/paths', path) + '/' + method
                if method not in b:
                    self.emit('breaking', 'operation_removed', loc, 'Existing operation is no longer described.')
                elif method not in a:
                    self.emit('info', 'operation_added', loc, 'New operation added.')
                else:
                    compared += 1
                    self.operation(path, method, a, b)
            handled = METHODS | {'parameters', 'servers'}
            self.changed({k: v for k, v in a.items() if k not in handled},
                         {k: v for k, v in b.items() if k not in handled}, pointer('/paths', path),
                         'path_metadata_changed', 'Path metadata or extensions changed.')
        # Catch unused components, auth definitions, dialect changes and extensions conservatively.
        self.changed({k: v for k, v in old.items() if k != 'paths'},
                     {k: v for k, v in new.items() if k != 'paths'}, '/',
                     'document_metadata_changed', 'Document metadata, components or extensions changed; review anything not covered by specific findings.')
        self.findings.sort(key=lambda f: (f['location'], f['severity'], f['code'], f['message']))
        counts = {severity: sum(f['severity'] == severity for f in self.findings)
                  for severity in ('breaking', 'review', 'info')}
        status = 'breaking' if counts['breaking'] else 'review_required' if counts['review'] else 'no_detected_breakage'
        return dict(schema='apidelta-report-v1', perspective='existing clients upgrading to the new description',
                    status=status, counts=counts, operations_compared=compared, findings=self.findings,
                    limits='Static conservative subset analysis, not a full OpenAPI validator or proof of runtime compatibility. Review findings are unresolved.')


def compare(old, new):
    return Analyzer(old, new).run()


def demo():
    path = Path(__file__).resolve().parent / 'imd-openapi.json'
    original, digest = load(path)
    # Deliberately mutate only in memory: never call any described operation.
    proposed = copy.deepcopy(original)
    body = proposed['paths']['/requests/quote']['post']['requestBody']['content']['application/json']['schema']
    body['required'].append('clientVersion')
    body['properties']['clientVersion'] = {'type': 'string'}
    del proposed['paths']['/requests/capabilities']['get']
    report = compare(original, proposed)
    report['demo'] = 'Synthetic breaking revision of a real captured public description; not an observed service change.'
    report['baseline_sha256'] = digest
    report['baseline_source'] = 'https://api.imd.fun/openapi.json'
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('demo', help='offline demonstration against the bundled public IMD description')
    diff = sub.add_parser('compare', help='compare two local JSON descriptions')
    diff.add_argument('old')
    diff.add_argument('new')
    diff.add_argument('--output', help='new workspace JSON file; existing files are refused')
    args = parser.parse_args(argv)
    try:
        if args.command == 'demo':
            report = demo()
        else:
            old, old_hash = load(args.old)
            new, new_hash = load(args.new)
            report = compare(old, new)
            report['old_sha256'], report['new_sha256'] = old_hash, new_hash
        result = json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + '\n'
        output = getattr(args, 'output', None)
        if output:
            with path_in_workspace(output).open('x', encoding='utf-8') as stream:
                stream.write(result)
        else:
            sys.stdout.write(result)
        if args.command == 'demo':
            return 0
        return 1 if report['status'] == 'breaking' else 3 if report['status'] == 'review_required' else 0
    except (Invalid, OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print('apidelta: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
