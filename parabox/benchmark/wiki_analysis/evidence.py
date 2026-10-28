"""Project canonical Wiki sessions and raw action records into portable measurements."""

import gzip
import json
from pathlib import Path

from parabox.benchmark.evaluation.records import load
from parabox.util import digest_json, read, save, sha256


def normalized(snapshot):
    return {name.removeprefix('shared/wiki/'): digest for name, digest in snapshot['files'].items()}


def cases(directory, files):
    digest = files.get('cases.json')
    if digest is None:
        return {}
    raw = (directory / 'meta/artifacts' / digest).read_bytes()
    if sha256(raw) != digest:
        raise ValueError('Case inventory artifact hash mismatch')
    entries = json.loads(raw)
    result = {}
    for entry in entries:
        name = f"private/{entry['package']}/{entry['index']}"
        fingerprint = digest_json({key: entry[key] for key in ('input', 'expected')})
        if name in result and result[name] != fingerprint:
            raise ValueError('Conflicting cases under one index')
        result[name] = fingerprint
    return result


def project(row, directory):
    end_path = directory / 'end.json'
    if sha256(end_path.read_bytes()) != row['source']['end_sha256']:
        raise ValueError('Raw terminal record differs from released canonical session')
    incoming, outgoing = normalized(row['incoming']), normalized(row['outgoing'])
    projected = {key: row[key] for key in ('id', 'chain', 'model', 'initial_score', 'condition',
                                         'generation', 'package', 'block', 'end', 'grading', 'budget')}
    projected.update(incoming=incoming, outgoing=outgoing,
                     cases={'incoming': cases(directory, incoming), 'outgoing': cases(directory, outgoing)},
                     source=row['source'], actions=[], service=[])
    for event in row['service']:
        record = {key: event.get(key) for key in ('at', 'budget_used', 'canonical', 'requested', 'returned')}
        case = event.get('response', {}).get('case')
        record['case_sha256'] = (digest_json({key: case[key] for key in ('input', 'expected')})
                                 if isinstance(case, dict) and {'input', 'expected'} <= case.keys() else None)
        projected['service'].append(record)
    for path in sorted((directory / 'meta/actions').glob('*.json')):
        raw = path.read_bytes()
        action = json.loads(raw)
        command = action.get('arguments', {}).get('command', '')
        record = {key: action[key] for key in ('turn', 'index', 'tool', 'charge')}
        record.update(source_sha256=sha256(raw), completed_at=action['recorded_at'],
                      executed=action['tool'] == 'run_command' and action.get('result', '').startswith('exit_code='),
                      inherited_file_mentions=sorted(name for name in incoming if name in command))
        for side in ('before', 'after'):
            record[side] = {'solution': action[side]['solution'].get('sha256'),
                            'wiki': normalized(action[side]['wiki'])}
        projected['actions'].append(record)
    return projected


def export(bundle, source_root, output):
    bundle, source_root, output = Path(bundle), Path(source_root).resolve(), Path(output)
    if output.exists():
        raise ValueError('Use a new evidence directory')
    manifest, records = load(bundle)
    source_path = bundle / 'sources.json'
    if manifest['files'].get('sources.json') != sha256(source_path.read_bytes()):
        raise ValueError('Source mapping is not bound by the release manifest')
    sources = {item['id']: item for item in read(source_path)}
    rows = []
    for row in records:
        if row['protocol'] != 'persistent-wiki':
            continue
        source = sources[row['id']]
        path = (source_root / source['source_record']).resolve()
        if not path.is_relative_to(source_root) or source['sha256'] != row['source']['end_sha256']:
            raise ValueError('Invalid canonical source mapping')
        rows.append(project(row, path.parent))
    if not rows:
        raise ValueError('No persistent-Wiki sessions')
    output.mkdir(parents=True)
    payload = ''.join(json.dumps(row, sort_keys=True) + '\n' for row in sorted(rows, key=lambda row: row['id']))
    (output / 'inputs.jsonl.gz').write_bytes(gzip.compress(payload.encode(), mtime=0))
    save(output / 'manifest.json', {
        'schema': 'parabox-wiki-trajectories-v1', 'sessions': len(rows),
        'source_release_manifest_sha256': sha256((bundle / 'manifest.json').read_bytes()),
        'files': {'inputs.jsonl.gz': sha256((output / 'inputs.jsonl.gz').read_bytes())},
        'measurement': {
            'task_boundary': 'Completion time of the first edited snapshot, when its independent grade is 100.',
            'resources': 'Each charged unit has exactly one phase and action-effect or service category.',
            'case_identity': 'Package/index plus hash of input and expected output.',
            'file_changes': 'Normalized relative paths and byte hashes at each action and session boundary.',
            'inherited_file_mentions': 'Filename appears in a command; a review cue, separate from demonstrated reading or use.',
            'lineage': 'Exact predecessor output to successor input; new case contributions are tracked by content.',
            'source_evidence': 'Canonical release records and SHA-256-bound raw actions and case snapshots; model-authored text is not executed.',
        },
    })
    return len(rows)


def load_inputs(directory):
    directory = Path(directory)
    manifest = read(directory / 'manifest.json')
    raw = (directory / 'inputs.jsonl.gz').read_bytes()
    if sha256(raw) != manifest['files']['inputs.jsonl.gz']:
        raise ValueError('Measurement input digest mismatch')
    rows = [json.loads(line) for line in gzip.decompress(raw).splitlines()]
    if len(rows) != manifest['sessions'] or len({row['id'] for row in rows}) != len(rows):
        raise ValueError('Canonical measurement count mismatch')
    return rows
