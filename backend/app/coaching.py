"""Role-specific practice and source-checked report material."""
import re

from .store import AppError
from .validation import text


def evidence_location(ref):
    if 'page' in ref:
        return f'{ref["path"]} · 第 {ref["page"]} 页'
    return f'{ref["path"]} · L{ref["start"]}–{ref["end"]}'


def interview_angle(role):
    role = role.lower()
    if any(term in role for term in ('测试', 'qa', '质量')):
        return '你会如何复现问题，选择测试输入，并判断结果是否符合预期？'
    if any(term in role for term in ('产品', '设计', '交互', 'ux')):
        return '用户在哪一步遇到困难？你比较过哪些方案，为什么作出这个选择？'
    if any(term in role for term in ('研究', '科研', '数据', '算法', '分析')):
        return '你的结论依赖什么对照或指标？换一批样本时可以怎样复核？'
    if any(term in role for term in ('开发', '工程', '后端', '前端', 'java', '架构')):
        return '关键实现在哪一步？并发请求或依赖失败时，这个设计还能保证什么？'
    return '你负责的哪项决定最能体现这条要求？你用什么依据判断它有效？'


def demo_coaching(state):
    first, last = state['answers']
    row = next(r for r in state['project']['excerpts'] if r['id'] == last['excerpt_id'])
    field = 'code' if row['code'] else 'note'
    # Compose from the candidate's own words, without inventing a result or metric.
    phrases = []
    for answer in (first, last):
        phrase = re.split(r'(?<=[。！？])|\n', answer['text'].strip(), maxsplit=1)[0].strip()
        if len(phrase) > 180:
            phrase = re.split(r'[，；;]|,(?!\d)', phrase, maxsplit=1)[0]
        if 0 < len(phrase) <= 180:
            phrase = re.sub(r'^我(?=负责|比较|设计|为|实现|验证|对照|测试|复用|整理|分析|开发|走查|访谈)', '', phrase).rstrip('。；; ')
            if phrase and phrase not in phrases:
                phrases.append(phrase)
    line = '；'.join(phrases)
    return {'answer_id': last['id'], 'answer_quote': last['text'][:180], 'excerpt_id': row['id'],
            'source_field': field, 'work_quote': row[field].strip()[:180],
            'match': f'第二轮回答指向{evidence_location(row)}。' + (
                '这处依据来自你的页面说明，可以打开原页核对你描述的设计。' if field == 'note'
                else '对照这处作品原文，核对回答中哪些细节可以从作品直接看出。'),
            'gap': interview_angle(state['project']['target_role']), 'resume_line': line}


def checked_coaching(raw, state):
    if not isinstance(raw, dict):
        raise AppError('复盘缺少岗位反馈，请重试。', 502)
    answer = next((a for a in state['answers'] if a['id'] == raw.get('answer_id')), None)
    ref = next((r for r in state['project']['excerpts'] if r['id'] == raw.get('excerpt_id')), None)
    field = raw.get('source_field')
    aq, wq = text(raw.get('answer_quote'), 1000), text(raw.get('work_quote'), 1000)
    if (not answer or not ref or answer.get('excerpt_id') != ref['id'] or field not in ('code', 'note')
            or aq not in answer['text'] or wq not in ref.get(field, '')):
        raise AppError('岗位反馈的引文与本场回答或作品不符，请重试。', 502)
    line = '' if raw.get('resume_line') == '' else text(raw.get('resume_line'), 500)
    numbers = r'\d+(?:[.,]\d+)*(?:\s*[%％])?'
    facts = '\n'.join([wq, *(a['text'] for a in state['answers'])])
    if set(re.findall(numbers, line)) - set(re.findall(numbers, facts)):
        raise AppError('简历建议出现了材料中未提供的数字，请重试。', 502)
    return dict(answer_id=answer['id'], answer_quote=aq, excerpt_id=ref['id'], source_field=field,
                work_quote=wq, match=text(raw.get('match'), 1000), gap=text(raw.get('gap'), 1000), resume_line=line)
