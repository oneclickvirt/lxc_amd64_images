#!/usr/bin/env python3
"""Repair public container archives without changing application/package files."""
import argparse
import io
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

from image_ssh_identity import KEY_PATH, runtime_files


def member_name(name):
    value = PurePosixPath(name)
    if value.is_absolute() or '..' in value.parts:
        raise ValueError('Unsafe archive path')
    return str(value)


def inventory(path):
    names = set()
    with tarfile.open(path, 'r|xz') as archive:
        for member in archive:
            names.add(member_name(member.name))
    return names


def repair_tar(path, target):
    names = inventory(path)
    additions = runtime_files(names)
    removed = 0
    # Streaming preserves modes, owners, symlinks, hardlinks, PAX attributes
    # and file contents. Private key members are skipped, never extracted.
    with tarfile.open(path, 'r|xz') as source, tarfile.open(target, 'w|xz', preset=3) as output:
        for member in source:
            name = member_name(member.name)
            if KEY_PATH.fullmatch(name):
                removed += 1
                continue
            if name in additions:
                continue
            output.addfile(member, source.extractfile(member) if member.isfile() else None)
        for name, content in additions.items():
            payload = content.encode()
            member = tarfile.TarInfo('./' + name)
            member.uid = member.gid = 0
            member.mode = 0o644
            member.size = len(payload)
            output.addfile(member, io.BytesIO(payload))
    if any(KEY_PATH.fullmatch(name) for name in inventory(target)):
        raise ValueError('Repaired archive retains a builder SSH identity')
    return removed


def guest_path(root, name):
    # All edited parent directories must stay inside the disposable rootfs.
    path = root / name
    if not path.parent.resolve().is_relative_to(root.resolve()):
        raise ValueError('Rootfs identity path escapes the disposable directory')
    return path


def repair_directory(root):
    names = set()
    for prefix in ('usr/lib/systemd/system', 'lib/systemd/system', 'etc/systemd/system'):
        folder = root / prefix
        if folder.is_dir() and folder.resolve().is_relative_to(root.resolve()):
            for service in ('ssh', 'sshd'):
                if (folder / (service + '.service')).is_file() or (folder / (service + '.service')).is_symlink():
                    names.add(prefix + '/' + service + '.service')
    for name in ('usr/bin/ssh-keygen', 'bin/ssh-keygen'):
        path = root / name
        if path.is_file() and path.resolve().is_relative_to(root.resolve()):
            names.add(name)
    removed = 0
    for directory in ('etc/ssh', 'etc/dropbear'):
        folder = guest_path(root, directory)
        if not folder.is_dir():
            continue
        if not folder.resolve().is_relative_to(root.resolve()):
            raise ValueError('SSH identity directory escapes the disposable rootfs')
        for path in folder.iterdir():
            if KEY_PATH.fullmatch(directory + '/' + path.name):
                if path.is_dir() and not path.is_symlink():
                    raise ValueError('Unexpected directory in place of a host key')
                path.unlink()
                removed += 1
    for name, content in runtime_files(names).items():
        path = guest_path(root, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise ValueError('Refusing to overwrite a symbolic service configuration')
        path.write_text(content)
        path.chmod(0o644)
    return removed


def repair_zip(path, target):
    with tempfile.TemporaryDirectory(prefix='image-hostkeys-') as temporary, zipfile.ZipFile(path) as source:
        root = Path(temporary)
        members = {member_name(i.filename): i for i in source.infolist() if not i.is_dir()}
        if len(members) != 2 or 'rootfs.squashfs' not in members or not any(n in members for n in ('incus.tar.xz', 'lxd.tar.xz')):
            raise ValueError('Expected one native container metadata/rootfs pair')
        squashfs = root / 'original.squashfs'
        with source.open(members['rootfs.squashfs']) as input_file, squashfs.open('wb') as output:
            shutil.copyfileobj(input_file, output)
        subprocess.run(['unsquashfs', '-no-progress', '-d', str(root / 'rootfs'), str(squashfs)], check=True, timeout=300)
        removed = repair_directory(root / 'rootfs')
        rebuilt = root / 'rebuilt.squashfs'
        subprocess.run(['mksquashfs', str(root / 'rootfs'), str(rebuilt), '-noappend', '-no-progress',
                        '-comp', 'xz', '-processors', '2', '-mem', '256M'], check=True, timeout=600)
        with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as output:
            for name, member in members.items():
                if name == 'rootfs.squashfs':
                    output.write(rebuilt, name)
                else:
                    # Metadata remains byte-for-byte identical.
                    with source.open(member) as input_file, output.open(member, 'w') as output_file:
                        shutil.copyfileobj(input_file, output_file)
    return removed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('files', nargs='+', type=Path)
    args = parser.parse_args()
    for path in args.files:
        if path.name != str(path) or path.is_symlink() or not path.is_file():
            raise ValueError('Expected a regular local release asset filename')
        target = path.with_suffix(path.suffix + '.safe')
        try:
            if path.name.endswith('.tar.xz'):
                removed = repair_tar(path, target)
            elif path.name.endswith('.zip') and not path.name.endswith('_kvm.zip'):
                removed = repair_zip(path, target)
            else:
                raise ValueError('Only container rootfs repair is supported')
            os.replace(target, path)
        finally:
            target.unlink(missing_ok=True)
        print(f'SSH_IDENTITY_REPAIR image={path.name} removed={removed}', flush=True)


if __name__ == '__main__':
    main()
