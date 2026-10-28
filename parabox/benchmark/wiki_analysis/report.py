"""Stratified descriptive measures with chain and package-return trajectories."""

from collections import Counter, defaultdict
from pathlib import Path
import gzip
import json

from parabox.util import save, sha256
from .evidence import load_inputs
from .measure import trajectories


def aggregate(rows):
    counts = {key: sum(bool(row[key]) for row in rows) for key in (
        'normal', 'submitted', 'first_edit_full_score', 'wiki_changed', 'wiki_deleted',
        'private_requests', 'private_returns', 'private_requests_after_full_edit',
        'added_or_replaced_cases', 'newly_returned_cases_retained',
        'inherited_cases_from_earlier_agents', 'inherited_own_package_cases_from_earlier_agents',
        'inherited_file_mention_actions')}
    totals = {key: sum(row[key] for row in rows) for key in (
        'budget_used', 'private_requests', 'private_returns', 'private_requests_after_full_edit',
        'newly_returned_cases', 'newly_returned_cases_retained', 'new_case_contribution_delivered')}
    allocation = defaultdict(Counter)
    for row in rows:
        for phase, values in row['resource_allocation'].items():
            allocation[phase].update(values)
    edits = [row['first_edit_unit'] for row in rows if row['first_edit_unit'] is not None]
    return {'sessions': len(rows), 'chains': len({row['chain'] for row in rows}),
            'session_counts': counts, 'event_totals': totals,
            'mean_earned_score': sum(row['earned_score'] for row in rows) / len(rows),
            'mean_first_edit_unit': sum(edits) / len(edits) if edits else None,
            'first_edit_observations': len(edits),
            'resource_allocation': {phase: dict(values) for phase, values in sorted(allocation.items())}}


def analyze(directory):
    inputs = load_inputs(directory)
    sessions, chains = trajectories(inputs)
    groups = defaultdict(list)
    for row in sessions:
        dimensions = {'all': 'all', 'model': row['model'], 'initial_score': str(row['initial_score']),
                      'condition': row['condition'], 'generation': str(row['generation']),
                      'package': row['package'],
                      'model_initial_score': f"{row['model']}:{row['initial_score']}",
                      'model_condition': f"{row['model']}:{row['condition']}",
                      'model_generation': f"{row['model']}:{row['generation']}",
                      'model_condition_generation': f"{row['model']}:{row['condition']}:{row['generation']}",
                      'model_score_condition': f"{row['model']}:{row['initial_score']}:{row['condition']}",
                      'package_visit': 'return' if row['same_package_predecessor'] else 'first'}
        for dimension, value in dimensions.items():
            groups[dimension, value].append(row)
    return {'schema': 'parabox-wiki-trajectory-analysis-v1', 'sessions': len(sessions), 'chains': len(chains),
            'input_sha256': sha256((Path(directory) / 'inputs.jsonl.gz').read_bytes()),
            'implementation': {name: sha256(Path(__file__).with_name(name).read_bytes())
                               for name in ('measure.py', 'report.py')},
            'exact_handoffs': sum(len(chain['handoffs']) for chain in chains),
            'groups': [{'dimension': dimension, 'value': value, **aggregate(selected)}
                       for (dimension, value), selected in sorted(groups.items())]}, sessions, chains


def write(directory):
    directory = Path(directory)
    summary, sessions, chains = analyze(directory)
    save(directory / 'summary.json', summary)
    for name, rows in (('sessions', sessions), ('chains', chains)):
        raw = ''.join(json.dumps(row, sort_keys=True) + '\n' for row in rows).encode()
        (directory / (name + '.jsonl.gz')).write_bytes(gzip.compress(raw, mtime=0))
    return {'sessions': summary['sessions'], 'chains': summary['chains'], 'exact_handoffs': summary['exact_handoffs']}
