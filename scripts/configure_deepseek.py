#!/usr/bin/env python3
"""Run on the school server; keep API keys out of arguments and terminal output."""
import argparse
import copy
import datetime
import getpass
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.parse
import uuid


PROVIDER = 'personal-deepseek'


def merge_config(original, key, base_url, model, scope):
    config = copy.deepcopy(original)
    agents = config.setdefault('agents', {})
    interviewer = next((a for a in agents.get('list', []) if a.get('id') == 'interviewer'), None)
    if interviewer is None:
        raise ValueError('未找到 interviewer Agent，配置未修改。')
    providers = config.setdefault('models', {}).setdefault('providers', {})
    if PROVIDER in providers:
        raise ValueError('personal-deepseek 已存在，请检查现有配置后再调整。')
    providers[PROVIDER] = {
        'baseUrl': base_url, 'api': 'openai-completions', 'apiKey': key,
        'models': [{'id': model, 'name': model}],
    }
    ref = PROVIDER + '/' + model
    defaults = agents.setdefault('defaults', {})
    defaults.setdefault('models', {})[ref] = {}
    interviewer['model'] = {'primary': ref, 'fallbacks': []}
    if scope == 'defaults-and-interviewer':
        defaults['model'] = {'primary': ref, 'fallbacks': []}
    return config


def private_write(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(content)


def update_key(original, key):
    config = copy.deepcopy(original)
    provider = config.get('models', {}).get('providers', {}).get(PROVIDER)
    if not isinstance(provider, dict):
        raise ValueError('未找到 personal-deepseek，请先执行首次接入。')
    provider['apiKey'] = key
    return config


def main():
    parser = argparse.ArgumentParser(description='在学校服务器接入个人 DeepSeek API；先校验、备份，再切换。')
    parser.add_argument('--base-url', default='https://api.deepseek.com')
    parser.add_argument('--model', default='deepseek-flash')
    parser.add_argument('--scope', choices=['interviewer', 'defaults-and-interviewer'], default='interviewer')
    parser.add_argument('--check', action='store_true', help='用占位密钥校验配置格式，不修改配置或调用模型')
    parser.add_argument('--update-key', action='store_true', help='仅更新已有 personal-deepseek 的密钥，保留模型和 Agent 设置')
    args = parser.parse_args()
    url = urllib.parse.urlsplit(args.base_url)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('API 地址必须是无凭据、查询参数和片段的 HTTPS 基础地址。')
    if not args.model.strip() or any(ord(c) < 32 for c in args.model):
        raise ValueError('模型标识不能为空或含控制字符。')
    executable = shutil.which('openclaw')
    if not executable:
        raise ValueError('请在学校服务器运行，未找到 openclaw 命令。')
    version = subprocess.run([executable, '--version'], capture_output=True, text=True, timeout=30)
    if version.returncode or '2026.5.22' not in version.stdout:
        raise ValueError('此脚本适配学校 OpenClaw 2026.5.22，当前版本需重新核对。')
    root = Path(os.environ.get('OPENCLAW_STATE_DIR', str(Path.home() / '.openclaw'))).expanduser().resolve()
    path = Path(os.environ.get('OPENCLAW_CONFIG_PATH', str(root / 'openclaw.json'))).expanduser().absolute()
    if path.is_symlink():
        raise ValueError('配置文件是符号链接，请先核对实际配置路径。')
    before = path.read_bytes()
    original = json.loads(before)
    # Check the target before asking for credentials.
    def prepare(key):
        if args.update_key:
            return update_key(original, key)
        return merge_config(original, key, args.base_url, args.model, args.scope)
    prepare('placeholder')
    if args.update_key:
        provider = original['models']['providers'][PROVIDER]
        host = urllib.parse.urlsplit(provider.get('baseUrl', '')).hostname
        print('已有 API 主机：' + (host or '未设置'))
        print('仅更新 personal-deepseek 密钥，保留模型、API 地址和 Agent 设置。')
    else:
        print('API 地址：' + args.base_url)
        print('目标模型：' + PROVIDER + '/' + args.model)
        print('切换范围：' + ('仅 interviewer' if args.scope == 'interviewer' else '默认模型和 interviewer'))
    if args.check:
        key = 'validation-placeholder-not-a-real-key'
    else:
        if not os.isatty(0):
            raise ValueError('请在交互终端运行，以便隐藏输入 API Key。')
        key = getpass.getpass('个人 DeepSeek API Key（隐藏输入）：').strip()
        if not key or any(ord(c) < 32 for c in key):
            raise ValueError('API Key 不能为空或含控制字符。')
    candidate = prepare(key)
    encoded = (json.dumps(candidate, ensure_ascii=False, indent=2) + '\n').encode()
    with tempfile.TemporaryDirectory(prefix='.deepseek-stage-', dir=path.parent) as temp:
        staged = Path(temp) / 'openclaw.json'
        private_write(staged, encoded)
        env = dict(os.environ, OPENCLAW_CONFIG_PATH=str(staged), OPENCLAW_STATE_DIR=str(root))
        check = subprocess.run([executable, 'config', 'validate'], env=env,
                               capture_output=True, timeout=60)
        if check.returncode:
            raise ValueError('OpenClaw 拒绝候选配置，原配置未修改；校验输出已隐藏以免泄露凭据。')
        if args.check:
            print('配置格式校验通过；未保存密钥、未切换模型、未验证 API 连通性。')
            return
        # The installer and this standalone server script write the same configuration.
        lock = root / '.offerlab-install.lock'
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ValueError('其他 OfferLab 配置操作正在进行，请稍后重试。') from None
        try:
            os.close(fd)
            backup_dir = root / 'offerlab-backups' / ('deepseek-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
            backup_dir.mkdir(parents=True, mode=0o700)
            backup = backup_dir / 'openclaw.json'
            private_write(backup, before)
            if path.read_bytes() != before:
                raise ValueError('配置在准备期间发生变化，请重新运行。')
            os.replace(staged, path)
        finally:
            lock.unlink()
    print('配置已保存（权限 600），原配置备份：' + str(backup))
    print('尚未验证真实模型调用。未自动重启 Gateway；若未热加载，请按学校平台的进程管理方式重载。')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        if type(error) is ValueError:
            print(str(error))
        else:
            print('配置失败：文件读取、JSON 解析或校验命令执行异常；诊断详情已隐藏以保护凭据。')
        raise SystemExit(1)
