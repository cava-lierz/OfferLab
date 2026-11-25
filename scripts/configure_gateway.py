"""Run in the user's terminal; never prints or passes credentials as arguments."""
import getpass
import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if not os.isatty(0):
        raise SystemExit('请在交互式本机终端运行；不要通过聊天或命令行参数传入 Token。')
    token = getpass.getpass('输入学校 OpenClaw Gateway Token（隐藏输入）：').strip()
    if not token or any(ord(c) < 32 for c in token):
        raise SystemExit('Token 不能为空或含控制字符，配置未修改。')
    target = ROOT / '.env'
    content = target.read_text() if target.exists() else (ROOT / '.env.example').read_text()
    keys = {'OPENCLAW_TOKEN', 'OFFERLAB_MODE'}
    lines = [line for line in content.splitlines() if line.split('=', 1)[0].strip() not in keys]
    lines += ['OFFERLAB_MODE=openclaw', 'OPENCLAW_TOKEN=' + json.dumps(token)]
    fd, temporary = tempfile.mkstemp(prefix='.offerlab-env-', dir=ROOT)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write('\n'.join(lines) + '\n')
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print('已保存到本机 .env（权限 600）；请重启后端。Token 未输出。')


if __name__ == '__main__':
    main()
