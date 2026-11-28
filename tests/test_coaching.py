import tempfile
import unittest
from pathlib import Path

from backend.app.coaching import checked_coaching, demo_coaching, interview_angle
from backend.app.engine import Engine, markdown_report
from backend.app.provider import DemoProvider
from backend.app.store import Store, AppError


class CoachingTests(unittest.TestCase):
    def setUp(self):
        self.row = {'id': 'E1', 'path': 'study.md', 'start': 2, 'end': 2, 'code': 'Compared 3 designs.', 'url':'https://example.org/work'}
        self.work = {'id':'preview','url':'https://example.org/pr','sha':'a'*40,'title':'Study','excerpts':[self.row], 'target_role':'产品经理'}
        self.state = {'resume': '设计报名页原型', 'jd': '能比较多个原型', 'project': self.work, 'answers': [
            {'id': 'a1', 'text': '我比较了不同报名方案。'},
            {'id': 'a2', 'text': '我对照了 3 个不同设计。', 'excerpt_id': 'E1'}]}

    def test_roles_change_the_followup_for_identical_work(self):
        questions = []
        for role in ('测试开发', '后端工程师', '产品经理', '数据分析师'):
            self.work['target_role'] = role
            questions.append(DemoProvider().generate('decision', self.state)['question'])
        self.assertEqual(len(set(questions)), len(questions))
        for role, question in zip(('测试开发', '后端工程师', '产品经理', '数据分析师'), questions):
            self.assertIn(interview_angle(role), question)
            self.assertIn(self.state['jd'], question)

    def test_evidence_and_unsubstantiated_numbers_rejected(self):
        raw = demo_coaching(self.state)
        review = checked_coaching(raw, self.state)
        self.assertIn('3', review['resume_line'])
        for change in ({'answer_id': 'a1'}, {'answer_quote': '错误引文'}, {'excerpt_id': 'P2'},
                       {'source_field': 'note'}, {'work_quote': '不存在的片段'}, {'resume_line': '转化率提升 87%'}):
            with self.subTest(change=change), self.assertRaises(AppError): checked_coaching(raw | change, self.state)

    def test_team_attribution_and_missing_evidence(self):
        self.state['answers'][0]['text'] = '我们整理了对照结果。'
        self.assertTrue(demo_coaching(self.state)['resume_line'].startswith('我们'))
        for a in self.state['answers']:
            a['text'] = '没有可独立摘录的句子' * 30
        review = demo_coaching(self.state)
        self.assertEqual(checked_coaching(review, self.state)['resume_line'], '')

    def test_image_page_note_is_never_treated_as_extracted_text(self):
        self.row.update(code='', page=2, note='按钮显示最后一次提交的回执。')
        raw = demo_coaching(self.state)
        self.assertEqual(checked_coaching(raw, self.state)['source_field'], 'note')
        with self.assertRaises(AppError): checked_coaching(raw | {'source_field':'code'}, self.state)

    def test_adoption_is_idempotent_and_preserves_original_across_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'state.sqlite3')
            engine = Engine(store, {'demo': DemoProvider()})
            session = engine.create('产品经理', self.state['resume'], jd=self.state['jd'], main_count=1, project=self.work)
            sid = session['id']
            with self.assertRaises(AppError): engine.adopt_resume_line(sid,'新表述',None)
            engine.act(sid, 'retry'); current = engine.act(sid, 'start')
            for i, answer in enumerate(self.state['answers']):
                current = engine.act(sid, 'answer', answer | {'request_id': f'answer-00{i}', 'question_id': current['current']['id']})
            self.assertEqual(current['status'],'completed')
            adopted = engine.adopt_resume_line(sid, '比较报名方案并完成原型走查。', None)
            self.assertEqual(engine.adopt_resume_line(sid, adopted['adopted_resume_line'], None), adopted)
            with self.assertRaises(AppError): engine.adopt_resume_line(sid, '过时的草稿', None)
            reopened = Store(store.path).get(sid)
            self.assertEqual(reopened['resume'], self.state['resume'])
            self.assertEqual(reopened['report']['coaching'], current['report']['coaching'])
            self.assertIn('已采纳的简历表述：' + adopted['adopted_resume_line'], markdown_report(reopened))
