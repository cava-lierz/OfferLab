"""Import bounded, commit-pinned excerpts from a public GitHub pull request."""
import asyncio
import hashlib
import json
import re
from urllib.parse import quote

import httpx

from .store import AppError

PR_URL = re.compile(r'https://github\.com/([A-Za-z0-9-]+)/([\w.-]+)/pull/([1-9][0-9]{0,9})(?:/files)?/?', re.ASCII)
HUNK = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@')
FILE_LIMIT = 60


def excerpts(filename, patch, blob_url):
    """Use contiguous added lines, preserving GitHub's right-hand line numbers."""
    result, block = [], []
    line = None
    start = 0
    def flush():
        if block and any(row.strip() for row in block):
            end = start + len(block) - 1
            result.append({'path': filename, 'start': start, 'end': end, 'code': '\n'.join(block),
                           'url': f'{blob_url}#L{start}-L{end}'})
        block.clear()
    for row in patch.split('\n'):
        hunk = HUNK.match(row)
        if hunk:
            flush()
            line = int(hunk[1])
        elif line is not None and row.startswith('+'):
            if len(row) > 301:
                flush()
            else:
                if not block:
                    start = line
                block.append(row[1:])
                if len(block) == 10:
                    flush()
            line += 1
        else:
            flush()
            if line is not None and row.startswith(' '):
                line += 1
        if len(result) >= 8:
            return result
    flush()
    return result


async def github_json(client, path):
    async with client.stream('GET', path) as response:
        if response.status_code == 404:
            raise AppError('找不到这个公开 PR，请检查链接和仓库可见性。', 404)
        if response.status_code in (403, 429):
            raise AppError('GitHub 暂时限制匿名读取，请稍后再试。', 429)
        response.raise_for_status()
        data = bytearray()
        async for chunk in response.aiter_bytes():
            data.extend(chunk)
            if len(data) > 5_000_000:
                raise AppError('这个 PR 的改动过大，请选择范围较小的 PR。', 422)
        return json.loads(data)


async def import_pr(url):
    match = PR_URL.fullmatch(url.strip())
    if not match or match[2] in ('.', '..'):
        raise AppError('请输入完整的公开 GitHub PR 链接，例如 https://github.com/owner/repo/pull/1。', 422)
    owner, repo, number = match.groups()
    path = f'/repos/{owner}/{repo}/pulls/{number}'
    try:
        async with asyncio.timeout(25), httpx.AsyncClient(base_url='https://api.github.com', timeout=10,
                headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'OfferLab-project-interview'}) as client:
            pr = await github_json(client, path)
            files = await github_json(client, f'{path}/files?per_page={FILE_LIMIT}')
            latest = await github_json(client, path)
        if any(pr[side]['sha'] != latest[side]['sha'] for side in ('head', 'base')):
            raise AppError('PR 在读取期间有新提交，请重新导入。', 409)
        sha = pr['head']['sha']
        if not re.fullmatch('[0-9a-f]{40}', sha):
            raise ValueError
        rows = []
        for file in files:
            filename = file['filename']
            link = f'https://github.com/{owner}/{repo}/blob/{sha}/{quote(filename, safe="/")}'
            rows.extend(excerpts(filename, file.get('patch') or '', link))
        if not rows:
            raise AppError('预览范围内没有可引用的新增文本行。请选择包含代码、测试或文档改动的 PR。', 422)
        for i, row in enumerate(rows, start=1):
            row['id'] = f'E{i}'
        result = {'url': f'https://github.com/{owner}/{repo}/pull/{number}', 'title': pr['title'],
                  'sha': sha, 'file_count': pr['changed_files'], 'scanned_files': len(files), 'excerpts': rows}
        result['id'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
        return result
    except (httpx.TimeoutException, TimeoutError):
        raise AppError('读取 GitHub 超时，请重试。', 504) from None
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise AppError('暂时无法读取这个 PR，请稍后重试。', 502) from None
