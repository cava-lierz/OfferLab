"""Project interview snapshots and evidence binding across retries and revisions."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.engine import Engine, markdown_report
from backend.app.provider import DemoProvider
from backend.app.store import AppError, Store

try:
    import httpx
    from backend.app.project import excerpts, import_pr
except ImportError:
    httpx = None

URL = 'https://github.com/demo/work/pull/2'
SHA = 'a' * 40
PATCH = '@@ -2,2 +8,3 @@\n before\n-removed\n+added()\n+test()\n@@ -90,0 +88,1 @@\n+finish()'


@unittest.skipUnless(httpx, 'httpx is not installed')
class ImportTests(unittest.IsolatedAsyncioTestCase):
    async def fetch(self, responses):
        def handler(request):
            self.assertEqual(request.url.host, 'api.github.com')
            self.assertNotIn('authorization', request.headers)
            return responses.pop(0)
        client = httpx.AsyncClient(base_url='https://api.github.com', transport=httpx.MockTransport(handler))
        with patch('backend.app.project.httpx.AsyncClient', return_value=client):
            return await import_pr(URL)

    def metadata(self, sha=SHA):
        return httpx.Response(200, json={'head': {'sha': sha}, 'base': {'sha': 'b' * 40}, 'changed_files': 1, 'title': 'Demo'})

    async def test_pinned_rows_preserve_exact_lines_and_path(self):
        files = httpx.Response(200, json=[{'filename': 'my test.py', 'patch': PATCH}])
        data = await self.fetch([self.metadata(), files, self.metadata()])
        first, last = data['excerpts']
        self.assertEqual((first['start'], first['end'], first['code']), (9, 10, 'added()\ntest()'))
        self.assertEqual(last['url'], f'https://github.com/demo/work/blob/{SHA}/my%20test.py#L88-L88')
        self.assertNotEqual(first['id'], last['id'])

    async def test_invalid_url_rate_limit_missing_pr_and_changing_revision(self):
        with self.assertRaises(AppError):
            await import_pr('https://example.org/demo/work/pull/2')
        for responses, status in (([httpx.Response(429)], 429), ([httpx.Response(404)], 404),
                                  ([self.metadata(), httpx.Response(200, json=[]), self.metadata('c'*40)], 409),
                                  ([self.metadata(), httpx.Response(200, json=[]), self.metadata()], 422)):
            with self.assertRaises(AppError) as caught:
                await self.fetch(responses)
            self.assertEqual(caught.exception.status, status)

    def test_long_lines_are_skipped_without_shifting_anchors(self):
        data = excerpts('file', '@@ -0,0 +1,12 @@\n+' + 'x'*301 + '\n' + '\n'.join('+abc' for _ in range(11)), 'url')
        self.assertEqual([(r['start'],r['end']) for r in data], [(2,11), (12,12)])


class ProjectFlowTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        self.store = Store(Path(directory.name) / 'state.sqlite3')
        self.engine = Engine(self.store, {'demo': DemoProvider()})
        self.preview = {'id': 'd'*64, 'url': URL, 'sha': SHA, 'title': 'Example', 'excerpts': [
            {'id': 'E1', 'path': 'example.py', 'start': 2, 'end': 2, 'url': URL+'#line', 'code':'return saved'},
            {'id': 'E2', 'path': 'test.py', 'start': 3, 'end': 3, 'url': URL+'#test', 'code':'assert ready'}]}
        self.store.save_preview(self.preview)

    def test_expiry_and_selection_validation(self):
        for ids in ([], ['E3'], ['E1','E1']):
            with self.assertRaises(AppError): self.store.select_project(self.preview['id'], ids)
        with self.store.connection() as db:
            db.execute('UPDATE project_previews SET expires=0')
        with self.assertRaises(AppError) as caught: self.store.select_project(self.preview['id'], ['E1'])
        self.assertEqual(caught.exception.status, 410)

    def test_two_rounds_require_verified_pointer_persist_and_export(self):
        selected = self.store.select_project(self.preview['id'], ['E1'])
        claim = '我修复了重复保存问题'
        state = self.engine.create('项目面试', claim, main_count=1, project=selected)
        sid = state['id']
        self.engine.act(sid, 'retry'); first = self.engine.act(sid, 'start')
        self.assertIn(claim, first['current']['text'])
        payload = {'request_id':'first-answer', 'question_id':first['current']['id'], 'text':'我保存了请求标识'}
        second = self.engine.act(sid, 'answer', payload)
        self.assertIn(payload['text'], second['current']['text'])
        with self.assertRaises(AppError): self.engine.submit(sid, 'finish')
        answer = {'request_id':'second-answer', 'question_id':second['current']['id'], 'text':'根据唯一标识查找原记录。'}
        for invalid in (None, 'E2'):
            with self.assertRaises(AppError): self.engine.submit(sid, 'answer', answer | {'excerpt_id':invalid})
        self.assertEqual(len(self.store.get(sid)['answers']), 1)
        saved = self.engine.act(sid, 'answer', answer | {'excerpt_id':'E1'})
        self.assertEqual(saved['status'], 'completed')
        self.assertEqual(self.engine.submit(sid, 'answer', answer | {'excerpt_id':'E1'}), saved)
        with self.assertRaises(AppError): self.engine.submit(sid, 'answer', answer | {'excerpt_id':'E2'})
        export = markdown_report(Store(self.store.path).get(sid))
        for text in (claim, payload['text'], answer['text'], SHA, 'return saved', URL+'#line'):
            self.assertIn(text, export)
        self.assertNotIn('assert ready', export)
