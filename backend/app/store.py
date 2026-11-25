"""SQLite snapshots and expiring per-interview leases, shared across workers."""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class AppError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS interviews (
                id TEXT PRIMARY KEY, state TEXT NOT NULL,
                lease TEXT, lease_until REAL NOT NULL DEFAULT 0)""")
            db.execute('CREATE TABLE IF NOT EXISTS workers (id TEXT PRIMARY KEY, heartbeat REAL NOT NULL)')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, state):
        with self.connection() as db:
            db.execute("INSERT INTO interviews(id,state) VALUES (?,?)",
                       (state['id'], json.dumps(state, ensure_ascii=False)))

    def get(self, interview_id):
        with self.connection() as db:
            row = db.execute("SELECT state FROM interviews WHERE id=?", (interview_id,)).fetchone()
        if not row:
            raise AppError('面试记录不存在', 404)
        return json.loads(row[0])

    def list(self):
        with self.connection() as db:
            rows = db.execute("SELECT state FROM interviews ORDER BY rowid DESC LIMIT 100").fetchall()
        return [{k: s[k] for k in ('id', 'role', 'status', 'mode', 'created_at', 'updated_at', 'main_count')}
                | {'answered': len(s['answers']), 'generation': s.get('generation'),
                   'error': s.get('error'), 'revision': s.get('revision', 0)}
                for (raw,) in rows for s in [json.loads(raw)]]

    @contextmanager
    def lease(self, interview_id, seconds=180):
        owner = str(uuid.uuid4())
        with self.connection() as db:
            result = db.execute("""UPDATE interviews SET lease=?, lease_until=?
                WHERE id=? AND (lease IS NULL OR lease_until < ?)""",
                (owner, time.time() + seconds, interview_id, time.time()))
            if not result.rowcount:
                self.get(interview_id)
                raise AppError('该面试正在处理，请稍后刷新。中断任务的锁会自动释放。', 409)
        try:
            yield owner
        finally:
            with self.connection() as db:
                db.execute("UPDATE interviews SET lease=NULL, lease_until=0 WHERE id=? AND lease=?",
                           (interview_id, owner))

    def save(self, state, owner):
        state['updated_at'] = time.time()
        state['revision'] = state.get('revision', 0) + 1
        with self.connection() as db:
            result = db.execute("UPDATE interviews SET state=? WHERE id=? AND lease=? AND lease_until>=?",
                                (json.dumps(state, ensure_ascii=False), state['id'], owner, time.time()))
            if not result.rowcount:
                raise AppError('处理已过期，请刷新后重试', 409)

    def renew_lease(self, interview_id, owner, seconds):
        now = time.time()
        with self.connection() as db:
            result = db.execute('UPDATE interviews SET lease_until=? WHERE id=? AND lease=? AND lease_until>=?',
                                (now + seconds, interview_id, owner, now))
            if not result.rowcount:
                raise AppError('处理已过期，请刷新后重试', 409)

    def queued(self):
        with self.connection() as db:
            return [row[0] for row in db.execute("""SELECT id FROM interviews
                WHERE json_extract(state, '$.generation.status') = 'queued'
                ORDER BY json_extract(state, '$.generation.queued_at') LIMIT 20""")]

    def heartbeat(self, worker_id):
        with self.connection() as db:
            db.execute('INSERT OR REPLACE INTO workers(id, heartbeat) VALUES (?,?)', (worker_id, time.time()))

    def retire_worker(self, worker_id):
        with self.connection() as db:
            db.execute('DELETE FROM workers WHERE id=?', (worker_id,))
        self.recover_interrupted()

    def recover_interrupted(self):
        """Fence stopped workers before allowing another attempt; preserve all answers."""
        now = time.time()
        with self.connection() as db:
            live = {row[0] for row in db.execute('SELECT id FROM workers WHERE heartbeat>?', (now - 15,))}
            rows = db.execute("""SELECT id,state,lease FROM interviews
                WHERE json_extract(state, '$.generation.status')='running'""").fetchall()
            for interview_id, raw, owner in rows:
                state = json.loads(raw)
                job = state['generation']
                if job.get('worker_id') in live and now < job['deadline_at'] + 30:
                    continue
                state['error'] = '生成任务已中断，材料和回答已保存，请重新生成。'
                state['updated_at'] = now
                state['revision'] = state.get('revision', 0) + 1
                job.update(status='failed', phase='failed', finished_at=now)
                db.execute('UPDATE interviews SET state=?,lease=NULL,lease_until=0 WHERE id=? AND state=? AND lease IS ?',
                           (json.dumps(state, ensure_ascii=False), interview_id, raw, owner))
            db.execute('DELETE FROM workers WHERE heartbeat<?', (now - 60,))
