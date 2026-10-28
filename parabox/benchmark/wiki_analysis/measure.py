"""Observable session events and byte-exact cross-session lineage."""

from collections import Counter, defaultdict
from datetime import datetime


def stamp(value):
    return datetime.fromisoformat(value)


def changes(before, after):
    return {
        'added': sorted(after.keys() - before.keys()),
        'removed': sorted(before.keys() - after.keys()),
        'modified': sorted(key for key in before.keys() & after.keys() if before[key] != after[key]),
    }


def service_kind(event):
    name = event.get('canonical') or ''
    return 'private' if name.startswith('private/') else 'public' if name.startswith('public/') else 'other'


def measure(row):
    budget = [event for event in row['budget'] if event['accepted']]
    if [event['used'] for event in budget] != list(range(1, row['end']['budget_used'] + 1)):
        raise ValueError('Incomplete charged-unit ledger')
    by_unit = {event['used']: event for event in budget}
    services = {event['budget_used']: event for event in row['service']
                if event.get('budget_used') in by_unit}
    actions = [action for action in row['actions'] if action['charge']['accepted']]
    action_units = [action['charge']['used'] for action in actions]
    expected_units = {unit for unit, event in by_unit.items() if event['kind'] != 'example_request'}
    if len(set(action_units)) != len(action_units) or set(action_units) != expected_units:
        raise ValueError('Action coverage differs from charged-unit ledger')
    for action in actions:
        if action['charge'] != by_unit[action['charge']['used']]:
            raise ValueError('Action charge differs from budget ledger')
    if actions and (actions[0]['before']['wiki'] != row['incoming']
                    or actions[-1]['after']['wiki'] != row['outgoing']):
        raise ValueError('Action file boundaries differ from session exports')
    first_edit = next((action for action in actions
                       if action['before']['solution'] != action['after']['solution']), None)
    grade = row['grading']
    first_grade = grade.get('first_change')
    expected_hash = row.get('source', {}).get('first_change_action_sha256')
    if expected_hash and (not first_edit or first_edit['source_sha256'] != expected_hash):
        raise ValueError('First edit differs from the released action binding')
    if first_grade and (not first_edit or first_edit['turn'] != first_grade['turn']
                        or first_edit['charge']['used'] != first_grade['budget_used']):
        raise ValueError('First graded edit differs from action timeline')
    full_boundary = first_edit if first_grade and first_grade['score']['passed'] == 100 else None

    def phase(event):
        if full_boundary is None:
            return 'no_graded_full_first_edit'
        moment = stamp(event['at'])
        if moment < stamp(full_boundary['charge']['at']):
            return 'before_full_edit'
        if moment <= stamp(full_boundary['completed_at']):
            return 'during_full_edit'
        return 'after_full_edit'

    effects, details = Counter(), []
    action_by_unit = {}
    for action in actions:
        before, after = action['before'], action['after']
        solution = before['solution'] != after['solution']
        wiki = before['wiki'] != after['wiki']
        effect = ('both_changed' if solution and wiki else 'solution_only_changed' if solution
                  else 'wiki_only_changed' if wiki else 'neither_changed')
        if action['tool'] == 'run_command':
            label = 'command_' + effect if action['executed'] else 'command_without_execution_record'
        else:
            label = action['tool'] or 'invalid_action'
        effects[label] += 1
        action_by_unit[action['charge']['used']] = label
        details.append({'turn': action['turn'], 'index': action['index'],
                        'unit': action['charge']['used'], 'phase': phase(action['charge']),
                        'effect': label, 'wiki_changes': changes(before['wiki'], after['wiki']),
                        'inherited_file_mentions': action['inherited_file_mentions']})
    allocation = defaultdict(Counter)
    for event in budget:
        unit = event['used']
        label = ('service_' + service_kind(services.get(unit, {}))
                 if event['kind'] == 'example_request' else action_by_unit[unit])
        allocation[phase(event)][label] += 1
    requests = [event for event in row['service'] if service_kind(event) == 'private']
    returned = [event for event in requests if event.get('case_sha256')]
    incoming, outgoing = row['cases']['incoming'], row['cases']['outgoing']
    new_cases = {name: digest for name, digest in outgoing.items() if incoming.get(name) != digest}
    novel_returns = {(event['canonical'], event['case_sha256']) for event in returned
                     if incoming.get(event['canonical']) != event['case_sha256']}
    returned_retained = novel_returns & set(new_cases.items())
    delta = changes(row['incoming'], row['outgoing'])
    result = {key: row[key] for key in ('id', 'chain', 'model', 'initial_score', 'condition',
                                      'generation', 'package', 'block')}
    result.update(
        normal=row['end']['normal'], submitted=row['end']['action'] == 'submit',
        earned_score=grade['earned_score'] * 100,
        final_code_score=grade['final_score']['passed'],
        first_edit_score=first_grade['score']['passed'] if first_grade else None,
        first_edit_unit=first_edit['charge']['used'] if first_edit else None,
        first_edit_full_score=full_boundary is not None,
        budget_used=len(budget), budget_remaining=row['end']['remaining_budget'],
        resource_allocation={key: dict(value) for key, value in allocation.items()},
        command_effects=dict(effects), actions=details, wiki_changes=delta,
        wiki_changed=any(delta.values()), wiki_deleted=bool(delta['removed']),
        inherited_file_mention_actions=sum(action['executed'] and bool(action['inherited_file_mentions']) for action in actions),
        private_requests=len(requests), private_returns=len(returned),
        private_requests_after_full_edit=sum(phase(by_unit.get(event.get('budget_used'), event)) == 'after_full_edit'
                                             for event in requests),
        incoming_cases=len(incoming), outgoing_cases=len(outgoing),
        added_or_replaced_cases=len(new_cases), newly_returned_cases=len(novel_returns),
        newly_returned_cases_retained=len(returned_retained),
        removed_cases=len(incoming.keys() - outgoing.keys()),
        newly_returned_case_keys=sorted(name for name, digest in returned_retained),
    )
    if sum(sum(value.values()) for value in allocation.values()) != result['budget_used']:
        raise ValueError('Resource allocation does not conserve charged units')
    return result


def trajectories(inputs):
    grouped = defaultdict(list)
    for row in inputs:
        grouped[row['chain']].append(row)
    measured, chains = [], []
    for chain, rows in sorted(grouped.items()):
        rows.sort(key=lambda row: row['generation'])
        origins, previous, chain_rows, transfers = {}, None, [], []
        for index, row in enumerate(rows):
            current = measure(row)
            if previous is not None:
                if row['generation'] != previous['generation'] + 1:
                    raise ValueError('Missing generation in canonical chain')
                if row['incoming'] != previous['outgoing']:
                    raise ValueError('Successor input differs from predecessor output')
                if row['cases']['incoming'] != previous['cases']['outgoing']:
                    raise ValueError('Successor case inventory differs')
            incoming, outgoing = row['cases']['incoming'], row['cases']['outgoing']
            if previous is None:
                origins = {name: None for name in incoming}
            current['inherited_cases_from_earlier_agents'] = sum(origin is not None for origin in origins.values())
            current['inherited_own_package_cases_from_earlier_agents'] = sum(
                origin is not None and name.startswith('private/' + row['package'] + '/')
                for name, origin in origins.items())
            current['same_package_predecessor'] = next((earlier['id'] for earlier in reversed(rows[:index])
                                                       if earlier['package'] == row['package']), None)
            if previous is not None:
                transfers.append({'from': previous['id'], 'to': row['id'], 'exact_files': True,
                                  'cases_from_earlier_agents': current['inherited_cases_from_earlier_agents'],
                                  'own_package_cases_from_earlier_agents':
                                      current['inherited_own_package_cases_from_earlier_agents']})
            origins = {name: origins.get(name) if incoming.get(name) == digest else row['id']
                       for name, digest in outgoing.items()}
            current['has_successor'] = index + 1 < len(rows)
            current['new_case_contribution_delivered'] = (current['newly_returned_cases_retained']
                                                         if current['has_successor'] else 0)
            measured.append(current)
            chain_rows.append(current)
            previous = row
        chains.append({'chain': chain, 'model': rows[0]['model'], 'initial_score': rows[0]['initial_score'],
                       'condition': rows[0]['condition'], 'block': rows[0]['block'],
                       'sessions': len(rows), 'handoffs': transfers,
                       'trajectory': [{key: item[key] for key in (
                           'id', 'generation', 'package', 'earned_score', 'first_edit_unit',
                           'budget_used', 'private_requests', 'private_requests_after_full_edit',
                           'wiki_changes', 'incoming_cases', 'outgoing_cases',
                           'inherited_own_package_cases_from_earlier_agents',
                           'new_case_contribution_delivered', 'inherited_file_mention_actions')}
                                      for item in chain_rows]})
    return measured, chains
