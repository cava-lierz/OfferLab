"""Build an explicit allowlisted source archive; copied state/secrets never enter it."""
import importlib.util
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer', ROOT / 'openclaw/install_interviewer.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def package(target):
    sources = ['openclaw/install_interviewer.py', 'openclaw/DEPLOYMENT.md']
    sources += ['openclaw/interviewer/' + relative for relative in installer.FILES]
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target, 'w:gz') as archive:
        for relative in sources:
            path = ROOT / relative
            if path.is_symlink():
                raise ValueError('不打包符号链接')
            archive.add(path, arcname='offerlab-interviewer/' + str(Path(relative).relative_to('openclaw')), recursive=False)
    return len(sources)


if __name__ == '__main__':
    target = ROOT / 'data/offerlab-interviewer.tar.gz'
    count = package(target)
    print(f'已打包 {count} 个源码文件：{target}')
    print('不包含 .openclaw 副本、任何 .env、认证文件或会话历史。')
