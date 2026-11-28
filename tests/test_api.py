"""In-process ASGI contracts with short sync handlers run inline.

The test transport needs no sockets or thread-portal wakeups. Worker concurrency
and shutdown are tested separately in test_jobs.py; no live Gateway is called.
"""
import importlib.util
import os
import tempfile
import time
import asyncio
from unittest.mock import patch
import unittest

AVAILABLE = all(importlib.util.find_spec(name) is not None for name in ('fastapi', 'httpx', 'dotenv', 'multipart', 'pypdf'))


@unittest.skipUnless(AVAILABLE, 'backend dependencies are not installed')
class ApiTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.old_env = {name: os.environ.get(name) for name in ('OFFERLAB_MODE', 'OFFERLAB_DATA_DIR')}
        os.environ['OFFERLAB_MODE'] = 'demo'
        os.environ['OFFERLAB_DATA_DIR'] = cls.temp.name
        from backend.app.main import app
        cls.app = app

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
        for key, value in cls.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    async def asyncSetUp(self):
        import httpx
        async def inline(func, *args, **kwargs):
            return func(*args, **kwargs)
        self.dispatch = patch('fastapi.routing.run_in_threadpool', inline)
        self.dispatch.start()
        self.addCleanup(self.dispatch.stop)
        self.lifespan = self.app.router.lifespan_context(self.app)
        await self.lifespan.__aenter__()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.lifespan.__aexit__(None, None, None)

    async def wait_for(self, base, status):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = (await self.client.get(base)).json()
            if state['status'] == status:
                return state
            self.assertIsNone(state['error'])
            await asyncio.sleep(.02)
        self.fail(f'Background job did not reach {status}')

    async def test_http_end_to_end(self):
        result = await self.client.post('/api/interviews', json={'role': '项目实习生', 'resume': '我组织校园项目访谈，设计原型，并参与开发与验证，完成了团队合作项目。', 'main_count': 1})
        self.assertEqual(result.status_code, 201)
        base = '/api/interviews/' + result.json()['id']
        self.assertEqual(result.json()['generation']['status'], 'queued')
        await self.wait_for(base, 'ready')
        state = (await self.client.post(base + '/start')).json()
        payload = {'question_id': state['current']['id'], 'request_id': 'api-test-0001', 'text': '我负责原型设计，访谈了十二位同学，最终完成了上线。'}
        accepted = await self.client.post(base + '/answers', json=payload)
        self.assertEqual(accepted.status_code, 202)
        self.assertEqual(len(accepted.json()['answers']), 1)
        duplicate = await self.client.post(base + '/answers', json=payload)
        self.assertEqual(len(duplicate.json()['answers']), 1)
        await self.wait_for(base, 'active')
        accepted = await self.client.post(base + '/finish')
        self.assertEqual(accepted.status_code, 202)
        state = await self.wait_for(base, 'completed')
        self.assertEqual((await self.client.get(base)).json()['report'], state['report'])
        export = await self.client.get(base + '/export')
        self.assertEqual(export.status_code, 200)
        self.assertIn('text/markdown', export.headers['content-type'])
        self.assertIn('演示模式', export.text)

    async def test_create_replay_returns_current_state_without_restarting_plan(self):
        form = {'role': '测试岗位', 'resume': '我参与校园项目的调研、原型设计、测试与交付。',
                'jd': '岗' * 12000, 'practice_focus': '讲清楚自己的贡献', 'request_id': 'create-after-timeout'}
        first = (await self.client.post('/api/interviews', json=form)).json()
        base = '/api/interviews/' + first['id']
        ready = await self.wait_for(base, 'ready')
        replay = (await self.client.post('/api/interviews', json=form)).json()
        self.assertEqual(replay, ready)
        self.assertEqual(replay['jd'], form['jd'])
        self.assertEqual(replay['practice_focus'], form['practice_focus'])
        self.assertEqual((await self.client.post('/api/interviews', json=form | {'role': '另一个岗位'})).status_code, 409)
        await self.client.delete(base)
        self.assertEqual((await self.client.post('/api/interviews', json=form)).status_code, 410)

    async def test_delete_is_idempotent_and_isolates_the_selected_record(self):
        form = {'role': '删除测试', 'resume': '我组织校园项目访谈，设计原型，并参与开发与验证，完成了团队合作项目。'}
        removed = (await self.client.post('/api/interviews', json=form)).json()['id']
        kept = (await self.client.post('/api/interviews', json=form)).json()['id']
        path = '/api/interviews/' + removed
        for _ in range(2):
            response = await self.client.delete(path)
            self.assertEqual((response.status_code, response.content), (204, b''))
        self.assertEqual((await self.client.get(path)).status_code, 404)
        self.assertEqual((await self.client.get(path + '/export')).status_code, 404)
        remaining = [row['id'] for row in (await self.client.get('/api/interviews')).json()]
        self.assertIn(kept, remaining)
        self.assertNotIn(removed, remaining)

    async def test_validation_and_missing_record(self):
        self.assertEqual((await self.client.get('/api/interviews/missing')).status_code, 404)
        self.assertEqual((await self.client.post('/api/interviews', json={'role': '', 'resume': 'too short'})).status_code, 422)

    async def test_next_question_is_explicit_and_duplicate_click_does_not_skip(self):
        created = await self.client.post('/api/interviews', json={'role': '测试下一题', 'resume': '我负责校园项目的需求分析和原型设计，与开发同学协作完成了上线。', 'main_count': 2})
        base = '/api/interviews/' + created.json()['id']
        await self.wait_for(base, 'ready')
        state = (await self.client.post(base + '/start')).json()
        self.assertEqual((await self.client.post(base + '/next', json={})).status_code, 422)
        self.assertEqual((await self.client.post(base + '/next', json={'question_id': state['current']['id']})).status_code, 409)
        for index in range(2):
            response = await self.client.post(base + '/answers', json={'question_id': state['current']['id'], 'request_id': f'boundary-answer-{index}', 'text': '我完成了需求访谈、原型设计和上线验证。'})
            self.assertEqual(response.status_code, 202)
            state = await self.wait_for(base, 'active' if index == 0 else 'between_questions')
        payload = {'question_id': state['current']['id']}
        next_response = await self.client.post(base + '/next', json=payload)
        self.assertEqual(next_response.status_code, 200)
        self.assertEqual(next_response.json()['status'], 'active')
        self.assertEqual(next_response.json()['current']['main_index'], 1)
        repeated = await self.client.post(base + '/next', json=payload)
        self.assertEqual(repeated.json()['current'], next_response.json()['current'])
        self.assertEqual(len(repeated.json()['answers']), 2)

    async def test_slow_model_does_not_block_acceptance_or_status_reads(self):
        import threading
        from backend.app.main import engine
        from backend.app.provider import DemoProvider
        entered, release = threading.Event(), threading.Event()
        previous = engine.providers['demo']
        class Slow(DemoProvider):
            def generate(self, task, state):
                entered.set()
                release.wait(5)
                return super().generate(task, state)
        engine.providers['demo'] = Slow()
        try:
            created = await self.client.post('/api/interviews', json={'role': '测试慢调用', 'resume': '我负责校园项目的需求分析和原型设计，与开发同学协作完成了上线。'})
            self.assertEqual(created.status_code, 201)
            base = '/api/interviews/' + created.json()['id']
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(.02)
            self.assertTrue(entered.is_set())
            running = await self.client.get(base)
            self.assertEqual(running.json()['generation']['status'], 'running')
            repeat = await self.client.post(base + '/retry')
            self.assertEqual(repeat.status_code, 202)
            self.assertEqual(repeat.json()['generation']['id'], running.json()['generation']['id'])
            release.set()
            await self.wait_for(base, 'ready')
        finally:
            release.set()
            engine.providers['demo'] = previous

    async def test_upload_errors_and_text(self):
        response = await self.client.post('/api/resumes/parse', files={'file': ('test.txt', '我负责学校项目的需求梳理、设计、开发和测试，完成了上线验证。'.encode())})
        self.assertEqual(response.status_code, 200)
        self.assertIn('需求梳理', response.json()['text'])
        for filename, content in [('test.pdf', b'broken'), ('test.docx', b'content')]:
            self.assertEqual((await self.client.post('/api/resumes/parse', files={'file': (filename, content)})).status_code, 400)

    async def test_scanned_or_empty_pdf_requires_text(self):
        from pypdf import PdfWriter
        from io import BytesIO
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        output = BytesIO()
        writer.write(output)
        response = await self.client.post('/api/resumes/parse', files={'file': ('blank.pdf', output.getvalue())})
        self.assertEqual(response.status_code, 400)
        self.assertIn('OCR', response.json()['detail'])
