"""Dependency-free, sanitized real completion test. Writes no response content."""
import datetime
import json
import os
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]


def settings():
    values = {}
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text().splitlines():
            if not line.strip() or line.lstrip().startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            value = value.strip()
            if value.startswith('"'):
                value = json.loads(value)
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            values[key.strip()] = value
    for key in ('OPENCLAW_BASE_URL', 'OPENCLAW_TOKEN', 'OPENCLAW_MODEL', 'OPENCLAW_AGENT_ID'):
        if key in os.environ:
            values[key] = os.environ[key]
    return values


def main():
    started = time.monotonic()
    result = {'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'health_ok': False, 'completion_present': False, 'http_status': None, 'error': None,
              'phase': 'config', 'health_seconds': None, 'completion_seconds': None}
    try:
        config = settings()
        base_url = config.get('OPENCLAW_BASE_URL', 'http://127.0.0.1:18790').rstrip('/')
        token = config.get('OPENCLAW_TOKEN', '')
        if not token:
            result['error'] = 'TOKEN_NOT_CONFIGURED'
        else:
            opener = build_opener(ProxyHandler({}))
            result['phase'] = 'health'
            print('[1/2] 检查 SSH 隧道后的 Gateway 健康接口（最长等待 8 秒）…', flush=True)
            stage_started = time.monotonic()
            with opener.open(base_url + '/healthz', timeout=8) as response:
                result['health_ok'] = response.status == 200
            result['health_seconds'] = round(time.monotonic() - stage_started, 2)
            result['phase'] = 'completion'
            print('[2/2] 健康接口成功，正在进行最小模型调用（读取超时 150 秒）…', flush=True)
            stage_started = time.monotonic()
            payload = {'model': config.get('OPENCLAW_MODEL', 'openclaw'), 'stream': False,
                       'user': 'offerlab-check-' + str(uuid.uuid4()),
                       'messages': [{'role': 'user', 'content': '请只回复 OFFERLAB_OK，不调用任何工具。'}]}
            headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
            if config.get('OPENCLAW_AGENT_ID', '').strip():
                headers['x-openclaw-agent-id'] = config['OPENCLAW_AGENT_ID'].strip()
            request = Request(base_url + '/v1/chat/completions', data=json.dumps(payload).encode(), headers=headers)
            with opener.open(request, timeout=150) as response:
                result['http_status'] = response.status
                body = response.read(1_000_000)
                content = json.loads(body)['choices'][0]['message']['content']
                result['completion_present'] = isinstance(content, str) and bool(content.strip())
                if not result['completion_present']:
                    result['error'] = 'EMPTY_COMPLETION'
            result['completion_seconds'] = round(time.monotonic() - stage_started, 2)
    except HTTPError as error:
        result['http_status'] = error.code
        result['error'] = 'AUTH_FAILED' if error.code in (401, 403) else 'HTTP_ERROR'
    except (URLError, TimeoutError, OSError):
        result['error'] = 'CONNECTION_FAILED_OR_TIMEOUT'
    except (ValueError, KeyError, IndexError, TypeError):
        result['error'] = 'INVALID_CONFIG_OR_RESPONSE'
    result['elapsed_seconds'] = round(time.monotonic() - started, 2)
    if result['phase'] == 'completion' and result['completion_seconds'] is None:
        result['completion_seconds'] = round(time.monotonic() - stage_started, 2)
    target = ROOT / 'data/gateway-check.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print('脱敏结果已写入 data/gateway-check.json；不含 Token 或模型响应正文。')
    return 0 if result['completion_present'] else 1


if __name__ == '__main__':
    sys.exit(main())
