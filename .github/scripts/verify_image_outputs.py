#!/usr/bin/env python3
"""Verify the actual image archive format before publishing any batch."""

import argparse
import lzma
from pathlib import Path
import re
import tarfile
import zipfile


def verify(path, minimum=None, maximum=2 * 1024 * 1024 * 1024):
    path = Path(path)
    openwrt = path.name.startswith("openwrt_")
    alpine = path.name.startswith("alpine_")
    alpine = path.name.startswith("alpine_")
    if minimum is None:
        minimum = (1 if openwrt or alpine else 10) * 1024 * 1024
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.(zip|tar\.xz)", path.name) or path.name != str(path):
        raise ValueError("Invalid image output filename")
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected image was not built")
    if not minimum < path.stat().st_size <= maximum:
        raise ValueError("Image size is outside release limits")
    if path.name.endswith(".zip"):
        with zipfile.ZipFile(path) as archive:
            if not archive.infolist() or archive.testzip() is not None:
                raise ValueError("ZIP image integrity check failed")
            if alpine and not path.name.endswith('_kvm.zip'):
                names = [Path(member.filename).name for member in archive.infolist() if not member.is_dir()]
                if names.count('rootfs.squashfs') != 1 or sum(names.count(n) for n in ['incus.tar.xz','lxd.tar.xz']) != 1:
                    raise ValueError('Alpine ZIP requires exactly one rootfs and metadata pair')
                member = next(m for m in archive.infolist() if Path(m.filename).name == 'rootfs.squashfs')
                with archive.open(member) as rootfs:
                    if rootfs.read(4) != b'hsqs':
                        raise ValueError('Alpine ZIP rootfs is not SquashFS')
    else:
        # Consume the entire XZ stream to check its checksum, not just its first tar header.
        with lzma.open(path, "rb") as compressed:
            while compressed.read(1024 * 1024):
                pass
        with tarfile.open(path, "r|xz") as archive:
            names = {entry.name.removeprefix("./") for entry in archive}
            if not names:
                raise ValueError("Empty tar image archive")
            if alpine and "etc/alpine-release" not in names:
                raise ValueError("Alpine root filesystem identity is missing")
            if openwrt and "etc/openwrt_release" not in names:
                raise ValueError("OpenWrt root filesystem identity is missing")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    for filename in args.files:
        verify(filename)
    print("Verified image archives:", len(args.files))


if __name__ == "__main__":
    main()
