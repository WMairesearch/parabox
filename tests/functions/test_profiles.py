from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from parabox.benchmark import default_spec
from parabox.benchmark.functions.design import PROFILES, initial_files
from parabox.benchmark.prepare import check, prepare
from parabox.benchmark.protocol.design import build_plan
from parabox.benchmark.protocol.prompts import core_task
from parabox.benchmark.run import run
from parabox.util import save
from tests.benchmark.test_benchmark_run import FakeEngine


class FunctionProfileTests(unittest.TestCase):
    def test_registered_profiles_execute_without_provider_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / 'model.json'
            save(config, {'model': 'offline', 'api_key_env': 'NEVER_READ'})
            for profile, settings in PROFILES.items():
                with self.subTest(profile=profile):
                    reference = str(config) if settings['recipients'] else None
                    spec = default_spec({'candidate': str(config)}, reference,
                                        'sha256:' + 'a' * 64, function_profile=profile)
                    plan = build_plan(spec)
                    expected = settings['generations'] * settings['replicates'] * (
                        settings['recipients'] + 1) * len(settings['conditions'])
                    self.assertEqual(plan['counts']['total'], expected)
                    directory = root / profile
                    prepare(directory, spec)
                    check(directory)
                    engine = FakeEngine()
                    with patch('parabox.model.Client.complete', side_effect=AssertionError('Provider call')):
                        result = run(directory, authorize_session_cap=expected,
                                     deadline=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                                     core_engine=engine, wiki_engine=FakeEngine(),
                                     image_verifier=lambda image: None)
                    self.assertEqual(result['completed'], expected)
                    delivered = {}
                    for row, incoming, options in engine.calls:
                        self.assertEqual(core_task(row).prompts_record()['sha256'],
                                         '033d00ec4eae159029f5941b090657f223896d16830e8f24692ac4f883c8771b')
                        key = row['chain'], row['generation']
                        if key in delivered:
                            self.assertEqual(incoming, delivered[key])
                        delivered[key] = incoming
                        if row['generation'] == 1:
                            self.assertEqual(incoming, initial_files(row))
                        else:
                            for parent in row['incoming_from']:
                                self.assertIn(f'shared/{parent}.txt', incoming)

    def test_default_remains_two_generations_and_empty(self):
        spec = default_spec({'candidate': 'candidate.json'}, 'reference.json', 'sha256:' + 'a' * 64)
        self.assertEqual(spec['core']['generations'], 2)
        self.assertEqual(spec['core']['initial_record'], 'empty')
        self.assertEqual(build_plan(spec)['counts']['total'], 108)
