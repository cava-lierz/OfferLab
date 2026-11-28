"""Validate model output without trusting model-supplied transitions or citations."""
import json
from urllib.parse import urlsplit
from .store import AppError


def text(value, limit=3000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise AppError('模型返回了无效文本，请重试', 502)
    return value.strip()


def parse_json(raw):
    if not isinstance(raw, str) or len(raw) > 100_000:
        raise AppError('模型响应过大或不是文本', 502)
    raw = raw.strip()
    if raw.startswith('```') and raw.endswith('```'):
        raw = raw.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        raise AppError('模型没有返回有效 JSON，请重试', 502) from None
    if not isinstance(value, dict):
        raise AppError('模型输出结构不正确，请重试', 502)
    return value


def plan(value, count):
    items = value.get('questions')
    if not isinstance(items, list) or len(items) != count:
        raise AppError('模型生成的问题数量不正确，请重试', 502)
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise AppError('模型问题格式不正确', 502)
        question = {'topic': text(item.get('topic'), 100), 'question': text(item.get('question'))}
        if 'criterion' in item:
            question['criterion'] = text(item['criterion'], 1000)
        result.append(question)
    return result


def preparation_research(value):
    """Validate an agent-reported reference list without fetching its URLs."""
    if value is None:
        return None  # Older agents only return questions.
    statuses = ('used', 'no_match', 'unavailable', 'skipped')
    if not isinstance(value, dict) or value.get('status') not in statuses:
        raise AppError('面试官返回了无效的备课状态，请重试', 502)
    rows = value.get('sources')
    if not isinstance(rows, list) or len(rows) > 4 or bool(rows) != (value['status'] == 'used'):
        raise AppError('备课来源与检索状态不符，请重试', 502)
    sources = []
    for row in rows:
        if not isinstance(row, dict):
            raise AppError('备课来源格式不正确', 502)
        url = text(row.get('url'), 2048)
        try:
            parsed = urlsplit(url)
            if (parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username is not None
                    or any(c.isspace() or ord(c) < 32 or c in '<>\\' for c in url)):
                raise ValueError
        except ValueError:
            raise AppError('备课来源链接格式不正确', 502) from None
        title = ' '.join(text(row.get('title'), 300).split())
        if not any(item['url'] == url for item in sources):
            sources.append({'title': title, 'url': url})
    return {'status': value['status'], 'sources': sources}


def decision(value):
    if value.get('action') not in ('followup', 'next'):
        raise AppError('模型返回了无效的追问决策，请重试', 502)
    return {'action': value['action'], 'question': text(value.get('question')) if value['action'] == 'followup' else ''}


DIMENSIONS = ['表达结构', '项目深度', '岗位匹配', '反思能力']


def report(value, answers, mode):
    dimensions = value.get('dimensions')
    if not isinstance(dimensions, list) or len(dimensions) != len(DIMENSIONS):
        raise AppError('复盘维度不完整，请重试', 502)
    answer_map = {a['id']: a['text'] for a in answers}
    checked = []
    for name, item in zip(DIMENSIONS, dimensions):
        if not isinstance(item, dict) or item.get('name') != name:
            raise AppError('复盘维度格式不正确', 502)
        score = item.get('score')
        if score is not None and (type(score) is not int or not 0 <= score <= 100):
            raise AppError('复盘评分超出范围', 502)
        evidence = item.get('evidence')
        if not isinstance(evidence, list) or len(evidence) > 10:
            raise AppError('复盘引用格式不正确', 502)
        citations = []
        for citation in evidence:
            if not isinstance(citation, dict):
                raise AppError('复盘引用格式不正确', 502)
            answer_id = citation.get('answer_id')
            quote = text(citation.get('quote'), 2000)
            if not isinstance(answer_id, str) or answer_id not in answer_map or quote not in answer_map[answer_id]:
                raise AppError('复盘引用与原回答不符，已拒绝保存，请重试', 502)
            citations.append({'answer_id': answer_id, 'quote': quote})
        if score is not None and not citations:
            raise AppError('有评分的维度必须提供回答证据', 502)
        checked.append({'name': name, 'score': None if mode == 'demo' else score,
                        'feedback': text(item.get('feedback')), 'suggestion': text(item.get('suggestion')),
                        'evidence': citations})
    return {'summary': text(value.get('summary')), 'dimensions': checked,
            'sources': [], 'source_note': '能力评价依据本场回答和项目内评价标准。'}
