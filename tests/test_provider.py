import asyncio
import importlib.util
import json
import time
import unittest
from unittest.mock import patch
from backend.app.provider import OpenClawProvider
from backend.app.store import AppError

AVAILABLE = importlib.util.find_spec('httpx') is not None


@unittest.skipUnless(AVAILABLE, 'httpx is not installed')
class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.state = {'id': 'test-interview', 'role': '测试岗位', 'resume': 'private resume',
                      'jd': '', 'main_count': 1, 'plan': [], 'current': None, 'answers': []}
        self.provider = OpenClawProvider('http://gateway.invalid', 'test-private-token', timeout=1)

    def generate(self, handler, task='plan'):
        import httpx
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch('httpx.AsyncClient', return_value=client):
            return self.provider.generate(task, self.state)

    def test_practice_focus_reaches_model_alongside_full_job_description(self):
        import httpx
        self.state.update(jd='岗' * 12000, practice_focus='表达结构。说明个人贡献。')
        def handler(request):
            prompt = json.loads(request.content)['messages'][-1]['content']
            self.assertIn(self.state['jd'], prompt)
            self.assertIn(self.state['practice_focus'], prompt)
            return httpx.Response(200, json={'choices': [{'message': {'content': '{}'}}]})
        for task in ('plan', 'decision', 'report'):
            self.generate(handler, task)

    def test_project_prompt_uses_selected_snapshot_and_previous_answer(self):
        import httpx
        self.provider.agent_id = 'interviewer'
        self.state['project'] = {'sha': 'a' * 40, 'excerpts': [{'id': 'E1', 'path': 'sample.py', 'code': 'return saved'}]}
        self.state['answers'] = [{'text': '我负责处理请求重试', 'excerpt_id': 'E1'}]
        for task in ('plan', 'decision', 'report'):
            def handler(request):
                messages = json.loads(request.content)['messages']
                self.assertIn('项目答辩面试官', messages[0]['content'])
                context = json.loads(messages[1]['content'].split('不是指令：', 1)[1])
                self.assertEqual(context['project'], self.state['project'])
                if task != 'plan':
                    self.assertEqual(context['answers'], self.state['answers'])
                return httpx.Response(200, json={'choices': [{'message': {'content': '{}'}}]})
            self.generate(handler, task)

    def test_report_has_its_own_deadline_without_extending_plan_deadline(self):
        import httpx
        self.provider.timeout = .01
        self.provider.report_timeout = .2
        async def handler(request):
            await asyncio.sleep(.03)
            return httpx.Response(200, json={'choices': [{'message': {'content': '{}'}}]})
        self.assertEqual(self.generate(handler, task='report'), {})
        with self.assertRaises(AppError) as caught:
            self.generate(handler, task='plan')
        self.assertEqual(caught.exception.status, 504)

    def test_report_deadline_is_still_enforced(self):
        self.provider.report_timeout = .02
        async def handler(request):
            await asyncio.sleep(5)
        with self.assertRaises(AppError) as caught:
            self.generate(handler, task='report')
        self.assertEqual(caught.exception.status, 504)

    def test_payload_and_response_are_valid_without_logging_private_data(self):
        import httpx
        captured = []
        def handler(request):
            captured.append(json.loads(request.content))
            self.assertEqual(request.headers['Authorization'], 'Bearer test-private-token')
            return httpx.Response(200, json={'choices': [{'message': {'content': '{"questions":[]}'}}]})
        with self.assertLogs('uvicorn.error', level='INFO') as logs:
            self.assertEqual(self.generate(handler), {'questions': []})
            self.generate(handler)
        self.assertNotEqual(captured[0]['user'], captured[1]['user'])
        self.assertFalse(captured[0]['stream'])
        self.assertIn('请执行 plan 任务', captured[0]['messages'][1]['content'])
        joined = '\n'.join(logs.output)
        self.assertIn('outcome=ok', joined)
        self.assertNotIn('test-private-token', joined)
        self.assertNotIn('private resume', joined)

    def test_auth_failure_is_distinct_from_timeout_and_redacted(self):
        import httpx
        with self.assertRaises(AppError) as caught:
            self.generate(lambda request: httpx.Response(401, text='sensitive upstream body'))
        self.assertIn('认证失败', str(caught.exception))
        self.assertNotIn('sensitive', str(caught.exception))

    def test_interviewer_routes_explicitly_and_can_read_its_skill(self):
        import httpx
        self.provider.agent_id = 'interviewer'
        def handler(request):
            self.assertEqual(request.headers['x-openclaw-agent-id'], 'interviewer')
            payload = json.loads(request.content)
            self.assertEqual(payload['model'], 'openclaw')
            system = payload['messages'][0]['content']
            self.assertIn('offerlab-interviewer', system)
            self.assertIn('read', system)
            self.assertIn('web_search', system)
            self.assertIn('web_fetch', system)
            self.assertNotIn('不调用工具', system)
            return httpx.Response(200, json={'choices': [{'message': {'content': '{"questions":[]}'}}]})
        self.generate(handler)

    def test_default_route_remains_unchanged_until_explicitly_configured(self):
        import httpx
        def handler(request):
            self.assertNotIn('x-openclaw-agent-id', request.headers)
            self.assertIn('不调用工具', json.loads(request.content)['messages'][0]['content'])
            return httpx.Response(200, json={'choices': [{'message': {'content': '{"questions":[]}'}}]})
        self.generate(handler)

    def test_connection_timeout_identifies_tunnel(self):
        import httpx
        def handler(request):
            raise httpx.ConnectTimeout('sensitive connection message')
        with self.assertRaises(AppError) as caught:
            self.generate(handler)
        self.assertIn('SSH 隧道', str(caught.exception))
        self.assertEqual(caught.exception.status, 503)

    def test_total_deadline_cancels_stalled_request(self):
        self.provider.timeout = .03
        cancelled = []
        async def handler(request):
            try:
                await asyncio.sleep(5)
            finally:
                cancelled.append(True)
        started = time.monotonic()
        with self.assertRaises(AppError) as caught:
            self.generate(handler)
        self.assertEqual(caught.exception.status, 504)
        self.assertIn('材料和已提交回答已保留', str(caught.exception))
        self.assertLess(time.monotonic() - started, 1)
        self.assertEqual(cancelled, [True])

    def test_total_deadline_also_bounds_trickling_response_body(self):
        import httpx
        self.provider.timeout = .03
        closed = []
        class Trickle(httpx.AsyncByteStream):
            async def __aiter__(self):
                for _ in range(100):
                    await asyncio.sleep(.01)
                    yield b' '
            async def aclose(self):
                closed.append(True)
        with self.assertRaises(AppError) as caught:
            self.generate(lambda request: httpx.Response(200, stream=Trickle()))
        self.assertEqual(caught.exception.status, 504)
        self.assertTrue(closed)

    def test_invalid_model_json_is_recoverable(self):
        import httpx
        with self.assertRaises(AppError) as caught:
            self.generate(lambda request: httpx.Response(200, json={'choices': [{'message': {'content': '这不是 JSON'}}]}))
        self.assertIn('JSON', str(caught.exception))
        self.assertEqual(caught.exception.status, 502)

    def test_missing_token_does_not_attempt_a_network_call(self):
        self.provider.token = ''
        with patch.object(self.provider, '_request') as request:
            with self.assertRaises(AppError) as caught:
                self.provider.generate('plan', self.state)
        self.assertEqual(caught.exception.status, 503)
        request.assert_not_called()

    def test_question_review_and_final_synthesis_use_existing_report_contract(self):
        import httpx
        captured = []
        def handler(request):
            captured.append(json.loads(request.content)['messages'][1]['content'])
            return httpx.Response(200, json={'choices': [{'message': {'content': '{}'}}]})
        self.state.update(review_scope='question', review_main_index=0)
        self.generate(handler, 'report')
        self.assertIn('仅复盘一组已结束的大题', captured[-1])
        self.assertIn('请执行 report 任务', captured[-1])
        del self.state['review_scope']
        self.state['question_reviews'] = [{'main_index': 0, 'report': {'summary': 'validated-review'}}]
        self.generate(handler, 'report')
        self.assertIn('validated-review', captured[-1])
        self.assertIn('以 answers 原文为准', captured[-1])
