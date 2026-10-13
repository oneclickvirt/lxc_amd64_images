#!/usr/bin/env python3
"""Verify the actual image archive format before publishing any batch."""

import argparse
import lzma
from pathlib import Path
import re
import tarfile
import zipfile


def verify(path, minimum=10 * 1024 * 1024, maximum=2 * 1024 * 1024 * 1024):
    path = Path(path)
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
    else:
        # Consume the entire XZ stream to check its checksum, not just its first tar header.
        with lzma.open(path, "rb") as compressed:
            while compressed.read(1024 * 1024):
                pass
        with tarfile.open(path, "r|xz") as archive:
            if sum(1 for _ in archive) == 0:
                raise ValueError("Empty tar image archive")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    for filename in args.files:
        verify(filename)
    print("Verified image archives:", len(args.files))


if __name__ == "__main__":
    main()
