#!/usr/bin/env python3
"""Local project commands; existing scripts remain usable on their own."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = {
    'setup': ('安装本机依赖，首次创建 .env', ['bash', 'scripts/setup.sh']),
    'dev': ('启动前后端，--reload 开启后端热更新', ['bash', 'scripts/dev.sh']),
    'check': ('运行本地测试和前端构建，不调用模型', ['bash', 'scripts/check.sh']),
    'gateway-config': ('隐藏输入 Gateway Token，写入本机 .env', [sys.executable, 'scripts/configure_gateway.py']),
    'gateway-check': ('检查隧道并发起一次真实模型请求', [sys.executable, 'scripts/check_gateway.py']),
    'runs': ('通过 SSH 读取学校运行摘要，不发起模型请求', [sys.executable, 'scripts/inspect_openclaw_runs.py', '--ssh']),
    'package': ('打包 Agent 源码到 data/，不上传或部署', [sys.executable, 'scripts/package_interviewer.py']),
    'tunnel': ('以前台进程打开学校 SSH 隧道，Ctrl+C 关闭', [
        'ssh', '-N', '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=30',
        '-L', '127.0.0.1:18790:127.0.0.1:18789', 'openclaw',
    ]),
}


def main():
    parser = argparse.ArgumentParser(description='OfferLab 本机开发与运维入口（Python 标准库，无需先安装依赖）')
    commands = parser.add_subparsers(dest='command', required=True)
    for name, (description, _) in COMMANDS.items():
        command_parser = commands.add_parser(name, help=description, description=description)
        if name == 'dev':
            command_parser.add_argument('--reload', action='store_true', help='后端代码变更时自动重启')

    args = parser.parse_args()
    command = COMMANDS[args.command][1]
    if args.command == 'dev' and args.reload:
        command = [*command, '--reload']
    os.chdir(ROOT)
    # Replace the wrapper so signals and exit codes belong to the actual command.
    try:
        os.execvp(command[0], command)
    except FileNotFoundError:
        parser.exit(1, f'未找到 {command[0]}，请先安装该命令。\n')


if __name__ == '__main__':
    main()
