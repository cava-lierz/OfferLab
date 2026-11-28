"""Durability, responsiveness and late-worker fencing without a live Gateway."""
import threading
import time
import unittest

from backend.app.engine import Engine
from backend.app.jobs import JobRunner
from backend.app.provider import DemoProvider
from backend.app.store import AppError, Store
from tests import test_engine


class JobTests(unittest.TestCase):
    setUp = test_engine.EngineTests.setUp
    create = test_engine.EngineTests.create
    start = test_engine.EngineTests.start

    def test_concurrent_creation_queues_one_durable_plan(self):
        from concurrent.futures import ThreadPoolExecutor
        barrier = threading.Barrier(2)
        def create():
            barrier.wait(timeout=5)
            return self.engine.create('测试', '这是用于并发测试的一段虚构简历和项目经历。', request_id='same-create')
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(create) for _ in range(2)]
            first, second = [future.result() for future in futures]
        self.assertEqual(first, second)
        self.assertEqual(Store(self.path).queued(), [first['id']])

    def test_answer_acknowledged_before_model_runs(self):
        state = self.start()
        self.provider.fail = 'decision'
        payload = {'request_id': 'durable-answer', 'question_id': state['current']['id'], 'text': '我负责了项目原型。'}
        accepted = self.engine.submit(state['id'], 'answer', payload)
        self.assertEqual(accepted['generation']['status'], 'queued')
        self.assertEqual(accepted['answers'][0]['text'], payload['text'])
        self.assertIsNone(accepted['error'])
        self.assertEqual(Store(self.path).get(state['id']), accepted)
        failed = self.engine.process_job(state['id'], 'test-worker')
        self.assertEqual(failed['generation']['status'], 'failed')
        self.assertEqual(failed['answers'], accepted['answers'])

    def test_queued_and_running_retries_do_not_duplicate_job(self):
        state = self.engine.submit(self.create()['id'], 'retry')
        self.assertEqual(self.engine.submit(state['id'], 'retry'), state)
        store, engine = self.store, self.engine
        class Observed(DemoProvider):
            def generate(inner, task, snapshot):
                running = store.get(state['id'])
                self.assertEqual(running['generation']['status'], 'running')
                self.assertEqual(engine.submit(state['id'], 'retry'), running)
                return super().generate(task, snapshot)
        self.engine.providers['demo'] = Observed()
        self.assertEqual(self.engine.process_job(state['id'], 'worker')['status'], 'ready')

    def test_duplicate_answer_is_acknowledged_while_worker_holds_lease(self):
        state = self.start()
        payload = {'request_id': 'duplicate-running', 'question_id': state['current']['id'], 'text': '我的具体贡献是设计。'}
        self.engine.submit(state['id'], 'answer', payload)
        engine = self.engine
        class Observed(DemoProvider):
            def generate(inner, task, snapshot):
                repeat = engine.submit(state['id'], 'answer', payload)
                self.assertEqual(len(repeat['answers']), 1)
                self.assertEqual(repeat['generation']['status'], 'running')
                with self.assertRaises(AppError):
                    engine.submit(state['id'], 'answer', payload | {'text': '不同内容'})
                return super().generate(task, snapshot)
        self.engine.providers['demo'] = Observed()
        self.engine.process_job(state['id'], 'worker')

    def test_queue_survives_restart_and_claims_once(self):
        state = self.engine.submit(self.create()['id'], 'retry')
        restarted_store = Store(self.path)
        restarted_store.recover_interrupted()
        self.assertIn(state['id'], restarted_store.queued())
        engine = Engine(restarted_store, {'demo': DemoProvider()})
        ready = engine.process_job(state['id'], 'new-worker')
        self.assertEqual(ready['status'], 'ready')
        self.assertEqual(engine.process_job(state['id'], 'second-worker'), ready)
        self.assertGreater(ready['revision'], state['revision'])

    def test_interrupted_worker_cannot_overwrite_new_attempt(self):
        state = self.engine.submit(self.create()['id'], 'retry')
        store, engine = self.store, self.engine
        replacement = []
        class Interrupted(DemoProvider):
            def generate(inner, task, snapshot):
                store.recover_interrupted()  # 'dead-worker' has no heartbeat
                failed = store.get(state['id'])
                self.assertEqual(failed['generation']['status'], 'failed')
                replacement.append(engine.submit(state['id'], 'retry')['generation']['id'])
                return super().generate(task, snapshot)
        self.engine.providers['demo'] = Interrupted()
        with self.assertRaises(AppError):
            self.engine.process_job(state['id'], 'dead-worker')
        actual = self.store.get(state['id'])
        self.assertEqual(actual['generation']['id'], replacement[0])
        self.assertEqual(actual['generation']['status'], 'queued')
        self.assertEqual(actual['plan'], [])

    def test_live_worker_survives_recovery_and_validation_is_visible(self):
        state = self.engine.submit(self.create()['id'], 'retry')
        self.store.heartbeat('live')
        phases = []
        original = self.store.save
        def observed(snapshot, owner):
            phases.append(snapshot['generation']['phase'])
            original(snapshot, owner)
            self.store.recover_interrupted()
        self.store.save = observed
        ready = self.engine.process_job(state['id'], 'live')
        self.assertEqual(ready['status'], 'ready')
        self.assertEqual(phases, ['generating', 'validating', 'completed'])

    def test_unexpected_provider_failure_is_recoverable_and_sanitized(self):
        class Broken(DemoProvider):
            def generate(self, task, state):
                raise RuntimeError('private-provider-detail')
        self.engine.providers['demo'] = Broken()
        state = self.engine.act(self.create()['id'], 'retry')
        self.assertEqual(state['generation']['status'], 'failed')
        self.assertNotIn('private-provider-detail', state['error'])

    def test_background_runner_completes_queued_job(self):
        state = self.engine.submit(self.create()['id'], 'retry')
        runner = JobRunner(self.engine)
        runner.start()
        try:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and Engine.pending(self.store.get(state['id'])):
                time.sleep(.02)
            self.assertEqual(self.store.get(state['id'])['status'], 'ready')
        finally:
            runner.stop()
            for thread in runner.threads:
                thread.join(timeout=1)

    def test_stop_fences_in_flight_job_without_waiting_for_model(self):
        entered, release = threading.Event(), threading.Event()
        class Slow(DemoProvider):
            def generate(self, task, state):
                entered.set()
                release.wait(3)
                return super().generate(task, state)
        self.engine.providers['demo'] = Slow()
        state = self.engine.submit(self.create()['id'], 'retry')
        runner = JobRunner(self.engine, concurrency=1)
        runner.start()
        try:
            self.assertTrue(entered.wait(2))
            runner.stop()
            self.assertEqual(self.store.get(state['id'])['generation']['status'], 'failed')
        finally:
            release.set()
            runner.stop()
            for thread in runner.threads:
                thread.join(timeout=1)
        self.assertEqual(self.store.get(state['id'])['status'], 'preparing')
