import copy
import unittest

from parabox.benchmark.wiki_analysis.evidence import normalized
from parabox.benchmark.wiki_analysis.measure import measure, trajectories
from parabox.benchmark.wiki_analysis.report import aggregate


def example():
    def charge(unit, second, kind):
        return {'accepted': True, 'used': unit, 'remaining': 20 - unit,
                'at': f'2026-01-01T00:00:{second:02d}+00:00', 'kind': kind}

    budget = [charge(1, 1, 'run_command'), charge(2, 2, 'example_request'),
              charge(3, 4, 'run_command'), charge(4, 5, 'example_request'), charge(5, 7, 'submit')]
    incoming = {'cases.json': 'old'}
    outgoing = {'cases.json': 'new'}
    actions = []
    for unit, turn, end_second, tool, before_solution, after_solution, before_wiki, after_wiki in (
            (1, 1, 3, 'run_command', 'initial', 'full', incoming, incoming),
            (3, 2, 6, 'run_command', 'full', 'full', incoming, outgoing),
            (5, 3, 8, 'submit', 'full', 'full', outgoing, outgoing)):
        actions.append({'turn': turn, 'index': 0, 'tool': tool, 'charge': budget[unit - 1],
                        'completed_at': f'2026-01-01T00:00:{end_second:02d}+00:00',
                        'before': {'solution': before_solution, 'wiki': before_wiki},
                        'after': {'solution': after_solution, 'wiki': after_wiki},
                        'executed': tool == 'run_command', 'inherited_file_mentions': []})
    return {'id': 'model-chain-1', 'chain': 'chain', 'model': 'model', 'initial_score': 60,
            'condition': 'full_wiki', 'generation': 1, 'package': 'events', 'block': 0,
            'end': {'normal': True, 'action': 'submit', 'budget_used': 5, 'remaining_budget': 15},
            'grading': {'earned_score': 1, 'final_score': {'passed': 100},
                        'first_change': {'turn': 1, 'budget_used': 1, 'score': {'passed': 100}}},
            'budget': budget, 'actions': actions, 'incoming': incoming, 'outgoing': outgoing,
            'cases': {'incoming': {'private/events/0': 'case0'},
                      'outgoing': {'private/events/0': 'case0', 'private/events/1': 'case1'}},
            'service': [{'budget_used': 2, 'at': budget[1]['at'], 'canonical': 'private/events/0',
                         'case_sha256': 'case0'},
                        {'budget_used': 4, 'at': budget[3]['at'], 'canonical': 'private/events/1',
                         'case_sha256': 'case1'}]}


class WikiTrajectoryTests(unittest.TestCase):
    def test_during_edit_requests_are_separate_from_later_requests(self):
        result = measure(example())
        self.assertEqual(result['private_requests_after_full_edit'], 1)
        self.assertEqual(result['resource_allocation']['during_full_edit']['service_private'], 1)
        self.assertEqual(result['resource_allocation']['after_full_edit']['service_private'], 1)
        self.assertEqual(sum(sum(values.values()) for values in result['resource_allocation'].values()), 5)

    def test_new_cases_require_retention_and_matching_content(self):
        row = example()
        self.assertEqual(measure(row)['newly_returned_cases_retained'], 1)
        row['cases']['outgoing']['private/events/1'] = 'different-content'
        self.assertEqual(measure(row)['newly_returned_cases_retained'], 0)

    def test_incomplete_actions_are_not_zero_work(self):
        row = example()
        row['actions'].pop(1)
        with self.assertRaisesRegex(ValueError, 'Action coverage'):
            measure(row)

    def test_nonfull_first_edit_has_no_full_score_boundary(self):
        row = example()
        row['grading']['first_change']['score']['passed'] = 90
        result = measure(row)
        self.assertFalse(result['first_edit_full_score'])
        self.assertEqual(result['private_requests_after_full_edit'], 0)
        self.assertEqual(set(result['resource_allocation']), {'no_graded_full_first_edit'})

    def test_paths_normalize_before_deletion_measurement(self):
        self.assertEqual(normalized({'files': {'shared/wiki/cases.json': 'hash'}}),
                         normalized({'files': {'cases.json': 'hash'}}))

    def test_case_delivery_and_repeated_package_are_separate_from_use(self):
        first = example()
        second = copy.deepcopy(first)
        second.update(id='model-chain-2', generation=2)
        second['incoming'] = first['outgoing']
        second['cases']['incoming'] = first['cases']['outgoing']
        for action in second['actions']:
            action['before']['wiki'] = first['outgoing']
            action['after']['wiki'] = first['outgoing']
        sessions, chains = trajectories([second, first])
        self.assertEqual(sessions[0]['new_case_contribution_delivered'], 1)
        self.assertEqual(sessions[1]['inherited_own_package_cases_from_earlier_agents'], 1)
        self.assertEqual(sessions[1]['inherited_file_mention_actions'], 0)
        self.assertEqual(sessions[1]['same_package_predecessor'], first['id'])
        self.assertEqual(len(chains[0]['handoffs']), 1)
        self.assertEqual(aggregate(sessions)['session_counts']['newly_returned_cases_retained'], 1)
        second['incoming'] = {}
        with self.assertRaisesRegex(ValueError, 'boundaries|Successor'):
            trajectories([first, second])
