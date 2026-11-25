import time
import uuid
from .store import AppError
from . import validation


def uid():
    return str(uuid.uuid4())


class Engine:
    def __init__(self, store, providers):
        self.store, self.providers = store, providers

    def create(self, role, resume, jd='', main_count=5, mode='demo'):
        if mode not in self.providers or type(main_count) is not int or not 1 <= main_count <= 5:
            raise AppError('无效的模式或问题数量')
        role, resume, jd = role.strip(), resume.strip(), jd.strip()
        if not 1 <= len(role) <= 100 or not 20 <= len(resume) <= 20000 or len(jd) > 12000:
            raise AppError('请填写职位（1–100 字）和简历（20–20000 字）；JD 最多 12000 字')
        state = {'id': uid(), 'role': role, 'resume': resume, 'jd': jd, 'main_count': main_count,
                 'mode': mode, 'status': 'preparing', 'plan': [], 'current': None, 'answers': [],
                 'report': None, 'error': None, 'generation': None, 'revision': 0, 'created_at': time.time(), 'updated_at': time.time()}
        self.store.create(state)
        # Return the durable ID before starting any slow network work.
        return state

    def _question(self, state, index, followup=0, question=None):
        return {'id': uid(), 'main_index': index, 'followup': followup,
                'topic': state['plan'][index]['topic'],
                'text': question or state['plan'][index]['question']}

    @staticmethod
    def pending(state):
        return (state.get('generation') or {}).get('status') in ('queued', 'running')

    @staticmethod
    def _duplicate(state, action, payload):
        if action != 'answer':
            return False
        prior = next((a for a in state['answers'] if a['request_id'] == payload.get('request_id')), None)
        if prior:
            if prior['text'] != payload.get('text', '').strip() or prior['question']['id'] != payload.get('question_id'):
                raise AppError('重复请求标识对应了不同内容', 409)
            return True
        return False

    def submit(self, interview_id, action, payload=None):
        """Acknowledge durable input without waiting for a model response."""
        payload = payload or {}
        # A running worker holds the write lease. Safe repeats only need a snapshot.
        state = self.store.get(interview_id)
        if self._duplicate(state, action, payload):
            return state
        if self.pending(state):
            if action == 'retry' or (action == 'finish' and state['status'] == 'reporting'):
                return state
            raise AppError('当前生成任务仍在进行，请等待结果后继续。', 409)
        with self.store.lease(interview_id) as owner:
            state = self.store.get(interview_id)
            if self._duplicate(state, action, payload):
                return state
            if self.pending(state):
                if action == 'retry' or (action == 'finish' and state['status'] == 'reporting'):
                    return state
                raise AppError('当前生成任务仍在进行，请等待结果后继续。', 409)
            if action == 'answer':
                request_id = payload.get('request_id')
                answer_text = payload.get('text', '').strip()
                question_id = payload.get('question_id')
                if not isinstance(request_id, str) or not 8 <= len(request_id) <= 100 or not 1 <= len(answer_text) <= 8000:
                    raise AppError('回答为 1–8000 字，且必须携带有效的请求标识')
                if state['status'] != 'active' or question_id != state['current']['id']:
                    raise AppError('此问题已回答或面试状态已变化，请刷新', 409)
                state['answers'].append({'id': uid(), 'request_id': request_id, 'text': answer_text,
                                         'question': state['current'].copy()})
                state['status'] = 'awaiting_next'
            elif action == 'start':
                if state['status'] != 'ready':
                    raise AppError('请先生成并确认面试计划', 409)
                state['current'] = self._question(state, 0)
                state['status'] = 'active'
            elif action == 'finish':
                if state['status'] == 'completed':
                    return state
                if state['status'] not in ('active', 'awaiting_next', 'reporting'):
                    raise AppError('面试尚未开始', 409)
                if not state['answers']:
                    raise AppError('至少回答一道题后再结束面试')
                state['status'] = 'reporting'
            elif action != 'retry':
                raise AppError('未知操作')
            task = {'preparing': 'plan', 'awaiting_next': 'decision', 'reporting': 'report'}.get(state['status'])
            state['error'] = None
            if task:
                provider = self.providers[state['mode']]
                budget = provider.timeout_for(task) if hasattr(provider, 'timeout_for') else 120
                state['generation'] = {
                    'id': uid(), 'task': task, 'status': 'queued', 'phase': 'queued',
                    'queued_at': time.time(), 'timeout_seconds': budget,
                }
            self.store.save(state, owner)
            return state

    def process_job(self, interview_id, worker_id):
        with self.store.lease(interview_id) as owner:
            state = self.store.get(interview_id)
            job = state.get('generation') or {}
            if job.get('status') != 'queued':
                return state
            now = time.time()
            self.store.renew_lease(interview_id, owner, max(180, job['timeout_seconds'] + 30))
            job.update(status='running', phase='generating', started_at=now,
                       deadline_at=now + job['timeout_seconds'], worker_id=worker_id)
            self.store.save(state, owner)

            def generate(provider, task):
                result = provider.generate(task, state)
                job['phase'] = 'validating'
                self.store.save(state, owner)
                return result

            try:
                self._advance(state, generate)
                job.update(status='completed', phase='completed', finished_at=time.time())
            except AppError as exc:
                state['error'] = str(exc)
                job.update(status='failed', phase='failed', finished_at=time.time())
            except Exception:
                # Never expose provider internals or leave unexpected failures spinning forever.
                state['error'] = '生成遇到异常，材料和回答已保存，请重试。'
                job.update(status='failed', phase='failed', finished_at=time.time())
            self.store.save(state, owner)
            return state

    def act(self, interview_id, action, payload=None):
        """Synchronous adapter for local engine tests; HTTP uses submit()."""
        state = self.submit(interview_id, action, payload)
        if (state.get('generation') or {}).get('status') == 'queued':
            return self.process_job(interview_id, 'synchronous')
        return state

    def _advance(self, state, generate):
        provider = self.providers[state['mode']]
        if state['status'] == 'preparing':
            state['plan'] = validation.plan(generate(provider, 'plan'), state['main_count'])
            state['status'] = 'ready'
        elif state['status'] == 'awaiting_next':
            current = state['current']
            choice = {'action': 'next'}
            if current['followup'] < 2:
                choice = validation.decision(generate(provider, 'decision'))
            if choice['action'] == 'followup':
                state['current'] = self._question(state, current['main_index'], current['followup'] + 1, choice['question'])
                state['status'] = 'active'
            elif current['main_index'] + 1 < state['main_count']:
                state['current'] = self._question(state, current['main_index'] + 1)
                state['status'] = 'active'
            else:
                state['status'] = 'reporting'
                # Persist this phase on return. A separate retry generates the report.
        elif state['status'] == 'reporting':
            state['report'] = validation.report(generate(provider, 'report'), state['answers'], state['mode'])
            state['status'] = 'completed'


def markdown_report(state):
    report = state['report']
    if not report:
        raise AppError('报告尚未生成', 409)
    lines = [f"# {state['role']} · 面试复盘", '',
             f"模式：{'演示模式（非模型评价）' if state['mode'] == 'demo' else 'OpenClaw'}", '', report['summary'], '']
    for item in report['dimensions']:
        lines += [f"## {item['name']} · {item['score'] if item['score'] is not None else '证据不足 / 未评分'}", '',
                  item['feedback'], '', '练习建议：' + item['suggestion'], '']
        for citation in item['evidence']:
            lines += ['回答 ' + citation['answer_id'], *['> ' + line for line in citation['quote'].splitlines()], '']
    lines += ['## 资料来源', '', report['source_note'], '', '评价仅用于训练反馈，不表示真实招聘录用概率。', '', '## 完整问答', '']
    for answer in state['answers']:
        lines += ['### ' + answer['question']['text'], '', answer['text'], '']
    return '\n'.join(lines)
