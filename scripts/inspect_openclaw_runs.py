"""Read-only diagnostics: never emits prompts, answers, tool arguments or secrets."""
import argparse
import datetime
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import build_opener, ProxyHandler


def timestamp(value):
    if isinstance(value, (int, float)):
        return value / 1000 if value > 100_000_000_000 else value
    if isinstance(value, str):
        try:
            return datetime.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
        except ValueError:
            pass
    return None


def identifier(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_./:-]{1,100}', value) else None


def error_kind(text):
    text = text.lower()
    for kind, patterns in (
        ('timeout', ('timeout', 'timed out', '超时')),
        ('aborted', ('abort', 'cancel')),
        ('file_missing', ('enoent', 'no such file', 'not found')),
        ('permission_denied', ('denied', 'not allowed', 'eacces', 'outside workspace')),
        ('rate_limited', ('rate limit', '429')),
    ):
        if any(p in text for p in patterns):
            return kind
    return 'other'


def trace_summary(path):
    events, calls, thinking = [], {}, None
    if not path.is_file():
        return {'trace_found': False}
    with path.open('rb') as stream:
        size = path.stat().st_size
        if size > 8_000_000:
            stream.seek(-8_000_000, 2)
            stream.readline()
        lines = stream.read().decode('utf-8', errors='replace').splitlines()
    task, started = None, None
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        at = timestamp(entry.get('timestamp') or entry.get('ts'))
        if entry.get('type') == 'thinking_level_change':
            level = entry.get('thinkingLevel')
            thinking = level if level in ('off', 'minimal', 'low', 'medium', 'high', 'xhigh', 'adaptive') else 'unknown'
        message = entry.get('message', {})
        if not isinstance(message, dict):
            continue
        role = message.get('role')
        content = message.get('content', [])
        if isinstance(content, str):
            content = [{'type': 'text', 'text': content}]
        if not isinstance(content, list):
            continue
        text = '\n'.join(x.get('text', '') for x in content if isinstance(x, dict) and isinstance(x.get('text'), str))
        if role == 'user':
            started = at or started
            for candidate in ('plan', 'decision', 'report'):
                if '请执行 ' + candidate + ' 任务' in text:
                    task = candidate
        elapsed = round(at - started, 2) if at is not None and started is not None else None
        if role == 'assistant':
            for block in content:
                if not isinstance(block, dict) or block.get('type') != 'toolCall':
                    continue
                arguments = block.get('arguments', {})
                target = arguments.get('path', arguments.get('file_path', '')) if isinstance(arguments, dict) else ''
                resource = 'other'
                if isinstance(target, str):
                    for filename in ('SKILL.md', 'rubric.json', 'questions.json'):
                        if target.endswith('/' + filename) or target == filename:
                            resource = filename
                name = identifier(block.get('name'))
                calls[block.get('id')] = resource
                events.append({'event': 'tool_call', 'tool': name, 'resource': resource, 'elapsed_seconds': elapsed})
            stop = message.get('stopReason')
            if stop in ('stop', 'length', 'error', 'aborted'):
                item = {'event': 'assistant_end', 'stop_reason': stop, 'text_chars': len(text), 'elapsed_seconds': elapsed}
                if stop in ('error', 'aborted'):
                    item['error_kind'] = error_kind(str(message.get('errorMessage', '')))
                events.append(item)
        elif role == 'toolResult':
            item = {'event': 'tool_result', 'tool': identifier(message.get('toolName')),
                    'resource': calls.get(message.get('toolCallId'), 'other'),
                    'is_error': bool(message.get('isError')), 'elapsed_seconds': elapsed}
            if item['is_error']:
                item['error_kind'] = error_kind(text)
            events.append(item)
    return {'trace_found': True, 'trace_truncated': size > 8_000_000,
            'task': task, 'thinking_level': thinking, 'events': events[-20:]}


def collect(state_dir):
    result = {'runs': []}
    for agent in ('interviewer', 'main'):
        directory = state_dir / 'agents' / agent / 'sessions'
        index = directory / 'sessions.json'
        if not index.is_file():
            continue
        entries = json.loads(index.read_text())
        selected = [(k, v) for k, v in entries.items() if 'offerlab-' in k and isinstance(v, dict)]
        selected.sort(key=lambda x: timestamp(x[1].get('updatedAt')) or 0, reverse=True)
        for _, entry in selected[:4]:
            report = entry.get('systemPromptReport') or {}
            tools = report.get('tools') or {}
            skills = report.get('skills') or {}
            item = {'agent': agent, 'session_id': identifier(entry.get('sessionId')),
                    'model': identifier(entry.get('model')), 'provider': identifier(entry.get('modelProvider')),
                    'updated_at': timestamp(entry.get('updatedAt')), 'aborted': bool(entry.get('abortedLastRun')),
                    'status': entry.get('status') if entry.get('status') in ('running', 'completed', 'error', 'idle', 'aborted') else None,
                    'runtime_ms': entry.get('runtimeMs') if isinstance(entry.get('runtimeMs'), (int, float)) else None,
                    'available_tools': [identifier(x.get('name')) for x in tools.get('entries', []) if isinstance(x, dict)],
                    'available_skills': [identifier(x.get('name')) for x in skills.get('entries', []) if isinstance(x, dict)]}
            # Read only a transcript basename under this agent's session directory.
            basename = Path(entry.get('sessionFile') or (str(entry.get('sessionId', 'missing')) + '.jsonl')).name
            path = directory / basename
            if path.suffix == '.jsonl' and not path.is_symlink():
                item.update(trace_summary(path))
                item['aborted'] = item['aborted'] or any(event.get('stop_reason') == 'aborted' for event in item.get('events', []))
            result['runs'].append(item)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ssh', action='store_true', help='从本机通过现有 openclaw SSH 别名读取脱敏诊断')
    args = parser.parse_args()
    if not args.ssh:
        print(json.dumps(collect(Path.home() / '.openclaw'), ensure_ascii=False, indent=2))
        return
    root = Path(__file__).resolve().parents[1]
    health = {}
    try:
        with build_opener(ProxyHandler({})).open('http://127.0.0.1:8000/api/health', timeout=5) as response:
            raw = json.loads(response.read(10000))
            health = {k: raw.get(k) for k in ('mode', 'agent_id', 'request_timeout_seconds')}
    except Exception:
        health = {'error': 'LOCAL_BACKEND_UNREACHABLE'}
    print('读取学校 Agent 运行摘要（不发起新的模型请求）…', flush=True)
    process = subprocess.run(['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                              'openclaw', 'python3', '-'], input=Path(__file__).read_text(),
                             capture_output=True, text=True, timeout=30)
    if process.returncode:
        raise SystemExit('SSH 诊断执行失败，请确认本机 ssh openclaw 可用。未输出远端原始错误。')
    try:
        result = json.loads(process.stdout)
    except ValueError:
        raise SystemExit('远端未返回有效诊断 JSON，未输出原始文本。') from None
    result['local_backend'] = health
    path = root / 'data/openclaw-runs.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print('已保存 data/openclaw-runs.json；不含简历、回答、Token 或工具参数。')


if __name__ == '__main__':
    main()
