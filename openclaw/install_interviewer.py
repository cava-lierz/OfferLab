#!/usr/bin/env python3
"""Install only OfferLab's agent; never import a copied cloud config into the server."""
import argparse
import copy
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

AGENT_ID = 'interviewer'
SKILL_NAME = 'offerlab-interviewer'
AGENT_TOOLS = ('read', 'web_search', 'web_fetch')
SOURCE = Path(__file__).resolve().parent / 'interviewer'
FILES = (
    'AGENTS.md', 'SOUL.md', 'IDENTITY.md', 'USER.md', 'HEARTBEAT.md',
    'skills/offerlab-interviewer/SKILL.md',
    'skills/offerlab-interviewer/references/questions.json',
    'skills/offerlab-interviewer/references/rubric.json',
)
MARKER = '.offerlab-agent.json'


def atomic_write(path, content, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.offerlab-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def merge_config(original, runtime_root):
    config = copy.deepcopy(original)
    agents = config.setdefault('agents', {})
    if 'entries' in agents:
        raise ValueError('检测到不同版本的 agents.entries 配置，请先适配该版本；未进行安装。')
    entries = agents.setdefault('list', [])
    if not isinstance(entries, list):
        raise ValueError('agents.list 格式不正确')
    defaults = agents.get('defaults', {})
    if not entries:
        entries.append({'id': 'main', 'default': True,
                        'workspace': defaults.get('workspace', str(runtime_root / 'workspace'))})
    existing = next((entry for entry in entries if entry.get('id') == AGENT_ID), None)
    # Updating workspace sources must retain a separately selected provider/model.
    model = existing.get('model') if existing is not None else None
    if model is None:
        model = defaults.get('model')
    if not model:
        raise ValueError('未发现现有默认模型，需先确认模型配置')
    desired = {
        'id': AGENT_ID, 'name': 'OfferLab 面试官',
        'workspace': str(runtime_root / 'workspace-interviewer'),
        'agentDir': str(runtime_root / 'agents/interviewer/agent'),
        'model': copy.deepcopy(model), 'skills': [SKILL_NAME],
        'tools': {'profile': 'coding', 'allow': list(AGENT_TOOLS),
                  'deny': ['exec', 'process', 'write', 'edit', 'apply_patch'],
                  'fs': {'workspaceOnly': True}},
    }
    if existing is not None:
        existing.update(desired)
    else:
        entries.append(desired)
    return config


def install(state_dir, runtime_root, validator=None):
    state_dir, runtime_root = Path(state_dir).resolve(), Path(runtime_root)
    if not runtime_root.is_absolute():
        raise ValueError('运行目录必须是绝对路径')
    config_path = state_dir / 'openclaw.json'
    workspace = state_dir / 'workspace-interviewer'
    if config_path.is_symlink() or workspace.is_symlink():
        raise ValueError('配置或目标工作区是符号链接，请先核对实际目录')
    original_bytes = config_path.read_bytes()
    original = json.loads(original_bytes)
    version = original.get('meta', {}).get('lastTouchedVersion', '')
    if version != '2026.5.22':
        raise ValueError('此安装包针对已检查的 2026.5.22 配置，请先核对实际版本')
    existing = next((x for x in original.get('agents', {}).get('list', []) if x.get('id') == AGENT_ID), None)
    managed = workspace / MARKER
    if workspace.exists() or existing:
        if not managed.is_file() or json.loads(managed.read_text()).get('owner') != 'OfferLab':
            raise ValueError('interviewer 已存在且不属于本安装包，拒绝覆盖')
        if existing and existing.get('workspace') != str(runtime_root / 'workspace-interviewer'):
            raise ValueError('现有 interviewer 使用其他工作区，拒绝覆盖')
    for relative in FILES:
        source = SOURCE / relative
        if source.is_symlink() or not source.is_file():
            raise ValueError('安装包文件缺失或包含符号链接')
        if relative.endswith('.json'):
            json.loads(source.read_text())
    candidate = merge_config(original, runtime_root)
    candidate_bytes = (json.dumps(candidate, ensure_ascii=False, indent=2) + '\n').encode()
    lock = state_dir / '.offerlab-install.lock'
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError('已有安装锁；请确认其他安装已结束后再处理该锁') from None
    os.close(lock_fd)
    backup = None
    try:
        with tempfile.TemporaryDirectory(prefix='.offerlab-stage-', dir=state_dir) as temporary:
            staged_config = Path(temporary) / 'openclaw.json'
            atomic_write(staged_config, candidate_bytes)
            if validator:
                validator(staged_config, state_dir)
            # Refuse to overwrite a config changed since we read it.
            if config_path.read_bytes() != original_bytes:
                raise ValueError('配置在准备期间发生变化，请重新安装以合并最新配置')
            name = datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
            backup = state_dir / 'offerlab-backups' / name
            backup.mkdir(parents=True, mode=0o700)
            atomic_write(backup / 'openclaw.json', original_bytes)
            if workspace.exists():
                shutil.copytree(workspace, backup / 'workspace-interviewer', symlinks=True)
            try:
                for relative in FILES:
                    destination = workspace / relative
                    # Prevent existing nested symlinks from redirecting writes.
                    if destination.is_symlink() or any(p.is_symlink() for p in destination.parents if p != state_dir.parent):
                        raise ValueError('工作区文件路径包含符号链接，拒绝写入')
                    atomic_write(destination, (SOURCE / relative).read_bytes(), 0o644)
                atomic_write(workspace / MARKER, b'{"owner":"OfferLab","version":1}\n')
                atomic_write(config_path, candidate_bytes)
            except Exception:
                atomic_write(config_path, original_bytes)
                if workspace.exists():
                    shutil.rmtree(workspace)
                if (backup / 'workspace-interviewer').exists():
                    shutil.copytree(backup / 'workspace-interviewer', workspace, symlinks=True)
                raise
    finally:
        lock.unlink(missing_ok=True)
    return {'agent_id': AGENT_ID, 'workspace': str(runtime_root / 'workspace-interviewer'),
            'skills': [SKILL_NAME], 'tools': list(AGENT_TOOLS), 'backup': str(backup),
            'validated_by_openclaw': validator is not None}


def validate_on_server(candidate, state_dir):
    executable = shutil.which('openclaw')
    if not executable:
        raise ValueError('未找到 openclaw 命令，请在学校终端运行安装')
    version = subprocess.run([executable, '--version'], capture_output=True, text=True, timeout=30)
    if version.returncode or '2026.5.22' not in version.stdout:
        raise ValueError('当前 OpenClaw 版本与安装包不一致，需先核对兼容性')
    env = dict(os.environ, OPENCLAW_CONFIG_PATH=str(candidate), OPENCLAW_STATE_DIR=str(state_dir))
    result = subprocess.run([executable, 'config', 'validate'], env=env, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise ValueError('OpenClaw 拒绝候选配置，原配置未修改；需核对该版本的 Agent、skills 或工具配置字段')


def main():
    parser = argparse.ArgumentParser(description='安装 OfferLab interviewer，保留服务器已有配置与凭据')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare-copy', type=Path, help='仅修改本地复制的 .openclaw，不能视为云端已部署')
    mode.add_argument('--install', action='store_true', help='在云端校验并安装到当前用户的 .openclaw')
    parser.add_argument('--remote-root', type=Path, help='准备副本时必须指定真实云端 .openclaw 绝对路径')
    args = parser.parse_args()
    if args.prepare_copy:
        if not args.remote_root:
            parser.error('--prepare-copy 必须搭配 --remote-root')
        result = install(args.prepare_copy, args.remote_root)
    else:
        if args.remote_root:
            parser.error('--remote-root 仅用于准备本地副本')
        root = Path.home() / '.openclaw'
        result = install(root, root, validate_on_server)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print('仅完成副本准备，尚未校验或部署到学校。' if args.prepare_copy else '安装与配置校验完成；请验证 Agent 加载。未自动重启 Gateway。')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        # Never print config contents or a subprocess's stdout/stderr.
        if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError):
            print('安装失败：' + str(error))
        else:
            print('安装失败：文件格式、文件访问或配置校验命令执行异常。')
        raise SystemExit(1)
