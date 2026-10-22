"""Fixed launchd entry point. Run with /usr/bin/python3 -I -S -B as {{USER}}."""
import datetime
import hashlib
import importlib
import json
import os
from pathlib import Path
import pwd
import stat
import sys
import uuid

PACKAGE = Path('/Library/Application Support/ClaudeDirectWallUpdater')
STATE = Path('{{HOME}}/Library/Application Support/ClaudeDirectWallUpdater')
ACCOUNT = '{{USER}}'


def verify_package(package, owner=0):
    """Every file is pinned; unexpected files, symlinks, or writable code stop execution."""
    entries = [package] + list(package.rglob('*'))
    for path in entries:
        info = path.lstat()
        if path.is_symlink() or info.st_uid != owner or info.st_mode & 0o022:
            raise RuntimeError('Unsafe package ownership or permissions')
        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise RuntimeError('Unexpected package entry')
    manifest = json.loads((package / 'sha256.json').read_text())
    actual = {str(p.relative_to(package)) for p in entries if p.is_file()} - {'sha256.json'}
    if not manifest or set(manifest) != actual:
        raise RuntimeError('Package file set mismatch')
    for name, digest in manifest.items():
        if hashlib.sha256((package / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Package hash mismatch')


def save_status(report):
    pending = STATE / ('.run-' + uuid.uuid4().hex + '.json')
    fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write('\n'); file.flush(); os.fsync(file.fileno())
    os.replace(pending, STATE / 'latest-system-run.json')


def main():
    os.umask(0o077)
    report = {'status': 'IN_PROGRESS', 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'pid': os.getpid(), 'parent_pid': os.getppid(), 'uid': os.geteuid(),
              'python': sys.executable, 'claude_started_or_restarted': False,
              'claude_requests_generated': False, 'direct_retry': False}
    # No imports of updater or YAML until account, state directory and code pass validation.
    account = pwd.getpwuid(os.geteuid())
    if os.geteuid() == 0 or account.pw_name != ACCOUNT or account.pw_dir != '{{HOME}}':
        raise RuntimeError('Unexpected service account')
    info = STATE.lstat()
    if STATE.is_symlink() or not STATE.is_dir() or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise RuntimeError('Unsafe state directory')
    code = 1
    try:
        verify_package(PACKAGE)
        report['package_verified'] = True
        # -I -S excludes user site, global site and PYTHONPATH. Only pinned dependencies are added.
        sys.path[0:0] = [str(PACKAGE), str(PACKAGE / 'vendor')]
        updater = importlib.import_module('update_shared_ip_wall')
        updater.BASE = STATE
        updater.CONFIG = Path('{{HOME}}/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev/clash-verge.yaml')
        sys.argv = [str(PACKAGE / 'update_shared_ip_wall.py'), '--apply']
        updater.main()
        report['status'] = 'APPLIED'; code = 0
    except Exception as error:
        # Parser errors may include credentials; record the type only.
        report.update(status='STOPPED_OLD_TARGETS_NOT_REMOVED', error_type=type(error).__name__)
    finally:
        report['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save_status(report)
        print(json.dumps(report, ensure_ascii=False), flush=True)
    return code


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print('System updater stopped:', type(error).__name__, flush=True)
        raise SystemExit(1)
