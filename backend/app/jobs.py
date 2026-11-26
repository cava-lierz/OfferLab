"""Bounded workers over SQLite's durable generation queue.

HTTP handlers only save input. Closing a browser does not cancel generation.
An interrupted running job is fenced and requires an explicit retry.
"""
import logging
import threading
import uuid

from .store import AppError

logger = logging.getLogger(__name__)


class JobRunner:
    def __init__(self, engine, concurrency=2):
        self.engine = engine
        self.store = engine.store
        self.id = str(uuid.uuid4())
        self.concurrency = concurrency
        self.stopped = threading.Event()
        self.threads = []

    def start(self):
        self.store.heartbeat(self.id)
        self.store.recover_interrupted()
        for target in [self._monitor] + [self._work] * self.concurrency + [self._review_work]:
            thread = threading.Thread(target=target, daemon=True, name='offerlab-jobs')
            self.threads.append(thread)
            thread.start()

    def stop(self):
        self.stopped.set()
        # Wake/join the monitor before retiring so it cannot restore our heartbeat.
        if self.threads:
            self.threads[0].join(timeout=3)
        self.store.retire_worker(self.id)
        for thread in self.threads[1:]:
            thread.join(timeout=0.1)

    def _monitor(self):
        while not self.stopped.wait(2):
            try:
                self.store.heartbeat(self.id)
                self.store.recover_interrupted()
            except Exception:
                logger.error('Job heartbeat failed; interrupted jobs will be recoverable')

    def _work(self):
        while not self.stopped.is_set():
            try:
                for interview_id in self.store.queued():
                    if self.stopped.is_set():
                        break
                    try:
                        self.engine.process_job(interview_id, self.id)
                    except AppError as exc:
                        if exc.status != 409:
                            logger.error('Job processing failed interview=%s status=%s', interview_id, exc.status)
                    finally:
                        if self.stopped.is_set():
                            self.store.retire_worker(self.id)
            except Exception:
                logger.error('Job queue unavailable; will retry')
            self.stopped.wait(0.5)

    def _review_work(self):
        # One separate slot keeps optional reviews from occupying every foreground worker.
        while not self.stopped.is_set():
            try:
                if not self.store.queued():
                    self.engine.process_review(self.id)
            except Exception:
                logger.error('Question review unavailable; interview remains usable')
            finally:
                if self.stopped.is_set():
                    self.store.retire_worker(self.id)
            self.stopped.wait(0.5)
