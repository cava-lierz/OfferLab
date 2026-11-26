import tempfile
import time
import unittest
from pathlib import Path
from backend.app.engine import Engine, markdown_report
from backend.app.provider import DemoProvider
from backend.app.store import AppError, Store
from backend.app.validation import parse_json
from backend.app.resume import extract_resume, MAX_BYTES


class ControlledProvider(DemoProvider):
    def __init__(self):
        self.fail = None
        self.always_followup = False
        self.forged_report = False
        self.bad_decision = False

    def generate(self, task, state):
        if task == self.fail:
            raise AppError('模拟网络超时', 504)
        if task == 'decision' and self.bad_decision:
            return {'action': 'delete_all'}
        if task == 'decision' and self.always_followup:
            return {'action': 'followup', 'question': '请补充你的具体贡献。'}
        result = super().generate(task, state)
        if task == 'report' and self.forged_report:
            result['dimensions'][0]['evidence'][0]['quote'] = '这句话从未出现在回答中。'
        return result


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'test.sqlite3'
        self.store = Store(self.path)
        self.provider = ControlledProvider()
        self.engine = Engine(self.store, {'demo': self.provider})

    def create(self, count=1):
        return self.engine.create('通用岗位', '我负责校园项目的需求分析、设计和实现，和同学协作完成交付。', main_count=count)

    def start(self, count=1):
        state = self.create(count)
        state = self.engine.act(state['id'], 'retry')
        self.assertEqual(state['status'], 'ready')
        return self.engine.act(state['id'], 'start')

    def answer(self, state, text='我亲自组织访谈并完成了需求优先级排序，收集反馈后调整了上线范围。', request_id='request-0001'):
        payload = {'question_id': state['current']['id'], 'request_id': request_id, 'text': text}
        return self.engine.act(state['id'], 'answer', payload), payload

    def test_full_flow_followup_report_and_export(self):
        state = self.start()
        state, _ = self.answer(state)
        self.assertEqual(state['current']['followup'], 1)
        state, _ = self.answer(state, request_id='request-0002')
        self.assertEqual(state['status'], 'reporting')
        state = self.engine.act(state['id'], 'retry')
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(len(state['report']['dimensions']), 4)
        self.assertTrue(all(d['score'] is None for d in state['report']['dimensions']))
        self.assertIn('演示模式（非模型评价）', markdown_report(state))
        self.assertIn(state['answers'][0]['text'], markdown_report(state))

    def test_forced_followups_are_bounded_by_backend(self):
        self.provider.always_followup = True
        state = self.start(5)
        for i in range(15):
            if state['status'] == 'between_questions':
                state = self.engine.act(state['id'], 'next', {'question_id': state['current']['id']})
            self.assertLessEqual(state['current']['followup'], 2)
            state, _ = self.answer(state, request_id=f'request-{i:04d}')
        self.assertEqual(state['status'], 'reporting')
        self.assertEqual(len(state['answers']), 15)
        self.assertEqual(state['current']['main_index'], 4)

    def test_idempotent_duplicate(self):
        state = self.start()
        state, payload = self.answer(state)
        duplicate = self.engine.act(state['id'], 'answer', payload)
        self.assertEqual(duplicate, state)
        self.assertEqual(len(duplicate['answers']), 1)

    def test_request_id_cannot_change_content(self):
        state, payload = self.answer(self.start())
        payload['text'] = '换一个回答'
        with self.assertRaises(AppError) as caught:
            self.engine.act(state['id'], 'answer', payload)
        self.assertEqual(caught.exception.status, 409)

    def test_old_question_rejected_even_with_new_request_id(self):
        state, payload = self.answer(self.start())
        payload['request_id'] = 'request-new'
        with self.assertRaises(AppError):
            self.engine.act(state['id'], 'answer', payload)
        self.assertEqual(len(self.store.get(state['id'])['answers']), 1)

    def test_network_failure_keeps_answer_and_retry_continues(self):
        state = self.start()
        self.provider.fail = 'decision'
        state, payload = self.answer(state)
        self.assertEqual(state['status'], 'awaiting_next')
        self.assertEqual(len(state['answers']), 1)
        self.assertEqual(state['error'], '模拟网络超时')
        self.assertEqual(self.engine.act(state['id'], 'answer', payload)['answers'], state['answers'])
        self.provider.fail = None
        state = self.engine.act(state['id'], 'retry')
        self.assertEqual(state['status'], 'active')
        self.assertEqual(state['current']['followup'], 1)
        self.assertIsNone(state['error'])

    def test_invalid_model_decision_does_not_lose_answer(self):
        self.provider.bad_decision = True
        state, _ = self.answer(self.start())
        self.assertEqual(state['status'], 'awaiting_next')
        self.assertIsNotNone(state['error'])
        self.assertEqual(len(self.store.get(state['id'])['answers']), 1)

    def test_failed_plan_can_be_recovered_by_saved_id(self):
        state = self.create()
        self.provider.fail = 'plan'
        failed = self.engine.act(state['id'], 'retry')
        self.assertEqual(failed['status'], 'preparing')
        self.provider.fail = None
        self.assertEqual(self.engine.act(state['id'], 'retry')['status'], 'ready')

    def test_forged_citation_is_rejected_and_retryable(self):
        state, _ = self.answer(self.start())
        self.provider.forged_report = True
        state = self.engine.act(state['id'], 'finish')
        self.assertEqual(state['status'], 'reporting')
        self.assertIsNone(state['report'])
        self.assertIn('原回答不符', state['error'])
        self.provider.forged_report = False
        self.assertEqual(self.engine.act(state['id'], 'retry')['status'], 'completed')

    def test_report_failure_does_not_reopen_interview(self):
        state, _ = self.answer(self.start())
        self.provider.fail = 'report'
        state = self.engine.act(state['id'], 'finish')
        self.assertEqual(state['status'], 'reporting')
        self.provider.fail = None
        state = self.engine.act(state['id'], 'retry')
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(self.engine.act(state['id'], 'finish'), state)

    def test_report_lease_covers_longer_model_deadline(self):
        state, _ = self.answer(self.start())
        store = self.store
        class SlowReportProvider(DemoProvider):
            def timeout_for(self, task):
                return 300 if task == 'report' else 120
            def generate(inner, task, snapshot):
                if task == 'report':
                    with store.connection() as db:
                        until = db.execute('SELECT lease_until FROM interviews WHERE id=?', (snapshot['id'],)).fetchone()[0]
                    self.assertGreater(until - time.time(), 320)
                    with self.assertRaises(AppError):
                        with store.lease(snapshot['id']):
                            self.fail('report lease must block a concurrent worker')
                return super().generate(task, snapshot)
        self.engine.providers['demo'] = SlowReportProvider()
        self.assertEqual(self.engine.act(state['id'], 'finish')['status'], 'completed')

    def test_expired_owner_cannot_renew_lease(self):
        state = self.create()
        with self.store.lease(state['id'], seconds=-1) as owner:
            with self.assertRaises(AppError):
                self.store.renew_lease(state['id'], owner, 330)

    def test_retry_clears_previous_error_before_calling_model(self):
        state = self.create()
        self.provider.fail = 'plan'
        failed = self.engine.act(state['id'], 'retry')
        self.assertIsNotNone(failed['error'])
        store = self.store
        class ObservedProvider(DemoProvider):
            def generate(inner, task, snapshot):
                self.assertIsNone(store.get(snapshot['id'])['error'])
                return super().generate(task, snapshot)
        self.engine.providers['demo'] = ObservedProvider()
        self.assertEqual(self.engine.act(state['id'], 'retry')['status'], 'ready')

    def test_restart_recovers_state(self):
        state, _ = self.answer(self.start())
        other = Store(self.path)
        self.assertEqual(other.get(state['id']), state)
        engine = Engine(other, {'demo': DemoProvider()})
        self.assertEqual(engine.act(state['id'], 'finish')['status'], 'completed')

    def test_concurrent_worker_cannot_take_active_lease(self):
        state = self.create()
        with self.store.lease(state['id']):
            other = Store(self.path)
            with self.assertRaises(AppError) as caught:
                with other.lease(state['id']):
                    self.fail('lease should reject')
            self.assertEqual(caught.exception.status, 409)
        self.assertEqual(self.engine.act(state['id'], 'retry')['status'], 'ready')

    def test_expired_lease_can_be_recovered_and_old_owner_cannot_save(self):
        state = self.create()
        with self.store.lease(state['id'], seconds=-1) as old_owner:
            with self.store.lease(state['id']) as new_owner:
                with self.assertRaises(AppError):
                    self.store.save(state, old_owner)
                self.store.save(state, new_owner)

    def test_sessions_are_isolated(self):
        first, second = self.start(), self.start()
        self.assertNotEqual(first['id'], second['id'])
        self.answer(first)
        self.assertEqual(self.store.get(second['id'])['answers'], [])
        self.assertEqual(len(self.store.list()), 2)
        self.assertNotIn('resume', self.store.list()[0])

    def test_empty_answer_cannot_advance(self):
        state = self.start()
        with self.assertRaises(AppError):
            self.answer(state, '   ')
        self.assertEqual(self.store.get(state['id'])['answers'], [])

    def test_cannot_finish_without_answer(self):
        with self.assertRaises(AppError):
            self.engine.act(self.start()['id'], 'finish')

    def test_missing_session_and_premature_export(self):
        with self.assertRaises(AppError) as caught:
            self.store.get('missing')
        self.assertEqual(caught.exception.status, 404)
        with self.assertRaises(AppError):
            markdown_report(self.start())

    def test_invalid_question_count(self):
        for count in (0, 6, True):
            with self.assertRaises(AppError):
                self.create(count)


class ParserTests(unittest.TestCase):
    def test_json_fence_and_malformed_output(self):
        self.assertEqual(parse_json('```json\n{"action":"next"}\n```'), {'action': 'next'})
        for value in ('not json', '[]', '{"action":', None, 'x' * 100001):
            with self.assertRaises(AppError):
                parse_json(value)

    def test_utf8_text_and_rejected_uploads(self):
        content = '我的项目经验包括需求分析、技术实现与团队协作，完成了一个校园系统。'
        self.assertEqual(extract_resume('resume.TXT', content.encode('utf-8-sig')), content)
        for name, data in [('a.txt', b''), ('a.docx', b'abc'), ('a.txt', b'abc'), ('a.txt', b'\xff' * 30), ('a.txt', b'x' * (MAX_BYTES + 1))]:
            with self.assertRaises(AppError):
                extract_resume(name, data)


if __name__ == '__main__':
    unittest.main()
