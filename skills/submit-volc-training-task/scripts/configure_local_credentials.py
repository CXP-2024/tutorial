#!/usr/bin/env python3
"""Save user-entered CLI credentials locally without the optional IAM list-keys check."""
import argparse
import configparser
import getpass
import os
from pathlib import Path
import tempfile


def update_config(path, values):
    if path.is_symlink():
        raise ValueError('Refusing to replace a symlinked configuration')
    config = configparser.ConfigParser(interpolation=None)
    if path.exists():
        with path.open() as stream:
            config.read_file(stream)
    if not config.has_section('default'):
        config.add_section('default')
    for key, value in values.items():
        if not value or any(c.isspace() for c in value):
            raise ValueError('Credential and region inputs must be nonempty and have no whitespace')
        config.set('default', key, value)
    fd, pending = tempfile.mkstemp(prefix='.configure-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            config.write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
    finally:
        if os.path.exists(pending):
            os.unlink(pending)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--region', required=True)
    args = parser.parse_args()
    ak = getpass.getpass('Access Key ID（隐藏输入）: ').strip()
    sk = getpass.getpass('Secret Access Key（隐藏输入）: ').strip()
    directory = Path.home() / '.volc'
    directory.mkdir(mode=0o700, exist_ok=True)
    update_config(directory / 'credentials', dict(access_key_id=ak, secret_access_key=sk))
    update_config(directory / 'config', dict(region=args.region))
    print('已保存本机CLI配置（文件权限0600）；未调用IAM校验，尚未验证平台权限。')


if __name__ == '__main__':
    main()
