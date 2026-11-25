import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('run_diagnostics', Path(__file__).resolve().parents[1] / 'scripts/inspect_openclaw_runs.py')
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)


class RunDiagnosticTests(unittest.TestCase):
    def test_tool_timing_and_abort_are_reported_without_private_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / 'agents/interviewer/sessions'
            directory.mkdir(parents=True)
            (directory / 'sessions.json').write_text(json.dumps({
                'agent:interviewer:openai-user:offerlab-test': {
                    'sessionId': 'fixture', 'sessionFile': '/cloud/fixture.jsonl',
                    'updatedAt': 1795589024199, 'runtimeMs': 120000,
                    'abortedLastRun': False, 'model': 'deepseek-reasoner', 'modelProvider': 'sjtu',
                    'systemPromptReport': {'private': 'SECRET_PROMPT', 'tools': {'entries': [{'name': 'read'}]},
                                           'skills': {'entries': [{'name': 'offerlab-interviewer'}]}},
                },
                'unrelated-user': {'sessionId': 'not-relevant'},
            }))
            entries = [
                {'timestamp': '2026-11-25T00:00:00Z', 'message': {'role': 'user', 'content': '请执行 report 任务。PRIVATE_ANSWER'}},
                {'timestamp': '2026-11-25T00:00:20Z', 'message': {'role': 'assistant', 'content': [
                    {'type': 'toolCall', 'id': 'read1', 'name': 'read', 'arguments': {'path': '/private/workspace/rubric.json'}}]}},
                {'timestamp': '2026-11-25T00:00:20.080Z', 'message': {'role': 'toolResult', 'toolName': 'read',
                    'toolCallId': 'read1', 'isError': False, 'content': 'SECRET_TOOL_CONTENT'}},
                {'timestamp': '2026-11-25T00:02:00Z', 'message': {'role': 'assistant', 'content': [],
                    'stopReason': 'aborted', 'errorMessage': 'aborted PRIVATE_ERROR'}},
            ]
            (directory / 'fixture.jsonl').write_text('\n'.join(json.dumps(x) for x in entries))
            report = diagnostics.collect(root)
            raw = json.dumps(report)
            for value in ('SECRET', 'PRIVATE', '/private', 'unrelated-user'):
                self.assertNotIn(value, raw)
            self.assertEqual(len(report['runs']), 1)
            run = report['runs'][0]
            self.assertTrue(run['aborted'])
            self.assertEqual(run['task'], 'report')
            self.assertEqual(run['events'][0]['resource'], 'rubric.json')
            self.assertEqual(run['events'][1]['elapsed_seconds'], 20.08)
            self.assertEqual(run['events'][2]['error_kind'], 'aborted')

    def test_missing_trace_does_not_claim_successful_tool_usage(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(diagnostics.trace_summary(Path(temporary) / 'missing.jsonl'), {'trace_found': False})
