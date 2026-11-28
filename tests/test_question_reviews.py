"""Question-level analysis overlaps later answers without sharing the interview lease."""
import threading
import unittest
from unittest.mock import patch

from backend.app.jobs import JobRunner
from backend.app.provider import DemoProvider
from backend.app.store import AppError, Store
from tests import test_engine


class QuestionReviewTests(unittest.TestCase):
    setUp = test_engine.EngineTests.setUp
    create = test_engine.EngineTests.create
    start = test_engine.EngineTests.start
    answer = test_engine.EngineTests.answer

    def boundary(self):
        state = self.start(2)
        state, _ = self.answer(state)
        state, _ = self.answer(state, request_id='request-0002')
        self.assertEqual(state['status'], 'between_questions')
        self.assertEqual(state['current']['main_index'], 0)
        return state

    def next(self, state):
        return self.engine.submit(state['id'], 'next', {'question_id': state['current']['id']})

    def review_rows(self):
        with self.store.connection() as db:
            return db.execute('SELECT status FROM question_reviews').fetchall()

    def test_next_is_immediate_and_idempotent_and_keeps_the_full_question_group(self):
        boundary = self.boundary()
        with patch.object(self.provider, 'generate', side_effect=AssertionError('next must not call the model')):
            current = self.next(boundary)
            self.assertEqual(self.next(boundary), current)
        self.assertEqual(current['status'], 'active')
        self.assertEqual(current['current']['main_index'], 1)
        self.assertEqual(current['current']['text'], current['plan'][1]['question'])
        self.assertEqual(self.review_rows(), [('queued',)])
        claim = self.store.claim_review('worker')
        self.assertEqual(claim['snapshot']['answers'], boundary['answers'])
        self.assertEqual(len(claim['snapshot']['answers']), 2)
        self.assertEqual(claim['snapshot']['current'], boundary['current'])
        self.assertIsNone(self.store.claim_review('another-worker'))

    def test_cannot_skip_an_unfinished_question_or_replay_a_stale_question(self):
        active = self.start(2)
        with self.assertRaises(AppError):
            self.next(active)
        boundary = self.boundary()
        with self.assertRaises(AppError):
            self.engine.submit(boundary['id'], 'next', {'question_id': 'wrong-question'})
        self.assertEqual(self.review_rows(), [])

    def test_transition_and_analysis_queue_are_one_transaction(self):
        boundary = self.boundary()
        # A database failure when enqueueing must also roll back the next question.
        with self.store.connection() as db:
            db.execute("CREATE TRIGGER reject_review BEFORE INSERT ON question_reviews BEGIN SELECT RAISE(ABORT, 'test'); END")
        with self.assertRaises(Exception):
            self.next(boundary)
        self.assertEqual(self.store.get(boundary['id']), boundary)
        self.assertEqual(self.review_rows(), [])

    def test_delete_discards_late_review_and_interview_writes(self):
        state = self.next(self.boundary())
        review = self.store.claim_review('worker')
        self.assertIsNotNone(review)
        with self.store.lease(state['id']) as owner:
            self.store.delete(state['id'])
            with self.assertRaises(AppError):
                self.store.save(state, owner, review=self.engine._review(state))
        self.assertFalse(self.store.finish_review(review, {'summary': 'late report'}))
        self.assertEqual(self.review_rows(), [])
        self.assertEqual(self.store.list(), [])

    def test_slow_review_does_not_block_answers_or_final_report(self):
        current = self.next(self.boundary())
        entered, release = threading.Event(), threading.Event()
        observed = []
        class SlowReview(DemoProvider):
            def generate(inner, task, snapshot):
                if snapshot.get('review_scope') == 'question':
                    observed.append(snapshot)
                    entered.set()
                    release.wait(5)
                return super().generate(task, snapshot)
        self.engine.providers['demo'] = SlowReview()
        thread = threading.Thread(target=self.engine.process_review, args=('worker',))
        thread.start()
        try:
            self.assertTrue(entered.wait(2))
            state, _ = self.answer(current, request_id='next-main-answer')
            self.assertEqual(state['current']['main_index'], 1)
            self.assertEqual(len(state['answers']), 3)
            finished = self.engine.act(state['id'], 'finish')
            self.assertEqual(finished['status'], 'completed')
            self.assertEqual(len(observed[0]['answers']), 2)
        finally:
            release.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.store.get(current['id']), finished)

    def test_final_report_reuses_validated_reviews_and_keeps_all_original_answers(self):
        state = self.next(self.boundary())
        self.assertTrue(self.engine.process_review('worker'))
        partial = self.store.completed_reviews(state['id'])
        self.assertEqual(len(partial), 1)
        self.assertEqual(partial[0]['main_index'], 0)
        observed = []
        class Observe(DemoProvider):
            def generate(inner, task, snapshot):
                if task == 'report':
                    observed.append(snapshot)
                return super().generate(task, snapshot)
        self.engine.providers['demo'] = Observe()
        state, _ = self.answer(state, request_id='later-answer')
        finished = self.engine.act(state['id'], 'finish')
        self.assertEqual(finished['status'], 'completed')
        self.assertEqual(observed[0]['question_reviews'], partial)
        self.assertEqual(observed[0]['answers'], finished['answers'])
        self.assertEqual(len(observed[0]['answers']), 3)
        self.assertNotIn('question_reviews', finished)

    def test_forged_or_failed_partial_review_does_not_break_final_report(self):
        state = self.next(self.boundary())
        self.provider.forged_report = True
        self.engine.process_review('worker')
        self.assertEqual(self.review_rows(), [('failed',)])
        self.assertEqual(self.store.completed_reviews(state['id']), [])
        self.assertEqual(self.store.get(state['id']), state)
        self.provider.forged_report = False
        self.assertEqual(self.engine.act(state['id'], 'finish')['status'], 'completed')

    def test_final_report_skips_unstarted_analysis(self):
        state = self.next(self.boundary())
        finished = self.engine.act(state['id'], 'finish')
        self.assertEqual(finished['status'], 'completed')
        self.assertEqual(self.review_rows(), [('skipped',)])
        self.assertFalse(self.engine.process_review('worker'))

    def test_restart_preserves_queue_and_fences_late_analysis(self):
        state = self.next(self.boundary())
        restarted = Store(self.path)
        restarted.recover_interrupted()
        claim = restarted.claim_review('dead-worker')
        self.assertIsNotNone(claim)
        restarted.recover_interrupted()
        self.assertFalse(restarted.finish_review(claim, {'stale': True}))
        self.assertEqual(self.review_rows(), [('failed',)])
        self.assertEqual(self.store.get(state['id']), state)

    def test_runner_starts_review_independently_and_shutdown_fences_result(self):
        state = self.next(self.boundary())
        entered, release = threading.Event(), threading.Event()
        class Slow(DemoProvider):
            def generate(inner, task, snapshot):
                if snapshot.get('review_scope') == 'question':
                    entered.set()
                    release.wait(5)
                return super().generate(task, snapshot)
        self.engine.providers['demo'] = Slow()
        runner = JobRunner(self.engine, concurrency=1)
        runner.start()
        try:
            self.assertTrue(entered.wait(2))
            state, _ = self.answer(state, request_id='answer-while-analyzing')
            self.assertEqual(len(state['answers']), 3)
            runner.stop()
            self.assertEqual(self.review_rows(), [('failed',)])
        finally:
            release.set()
            runner.stop()
            for thread in runner.threads:
                thread.join(2)
        self.assertEqual(self.store.completed_reviews(state['id']), [])
