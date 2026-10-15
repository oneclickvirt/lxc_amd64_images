#!/usr/bin/env python3
"""Retry classified transient image source failures within one build budget."""
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time

OUTPUTS = ('incus.tar.xz', 'lxd.tar.xz', 'meta.tar.xz', 'rootfs.squashfs',
           'rootfs.tar.xz', 'disk.qcow2', 'disk_compressed.qcow2')
NETWORK = re.compile(r"couldn.t download packages|failed retrieving file .* from .* (?:timed out|operation too slow)|HTTP[^\n]*(?:429|500|502|503|504)|connection (?:reset|refused)|temporary failure in name resolution|could not resolve host|TLS handshake timeout|unexpected EOF", re.I)
INTEGRITY = re.compile(r'bad signature|invalid signature|invalid checksum|hash sum mismatch|BADSIG|NO_PUBKEY|GPG check FAILED|certificate verify failed', re.I)
XATTR_ENODATA = re.compile(r'rsync:[^\n]*get_xattr_data:[^\n]*lgetxattr\([^\n]*"security[.]selinux"[^\n]*No data available \(61\)', re.I)


def retryable(log):
    # The Oracle ISO's nested rootfs copy can observe an SELinux label that
    # disappears before rsync reads it. Retry the whole fresh builder once;
    # never ignore an rsync exit, discard attributes or relax integrity checks.
    source_copy = 'Failed to unpack ISO' in log and XATTR_ENODATA.search(log)
    return bool(NETWORK.search(log) or source_copy) and not INTEGRITY.search(log)


def invoke(command, timeout):
    environment = os.environ.copy()
    environment.pop('GH_TOKEN', None)
    environment.pop('GITHUB_TOKEN', None)
    deadline = time.monotonic() + timeout
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               env=environment, start_new_session=True)
    tail = bytearray()
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                for key, _ in selector.select(min(1, remaining)):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        break
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.buffer.flush()
                    tail.extend(chunk)
                    if len(tail) > 262144:
                        del tail[:-262144]
        return process.wait(timeout=max(0.01, deadline-time.monotonic())), tail.decode(errors='replace')
    finally:
        # The builder can exit while a grandchild still holds stdout open.
        # Always reap its isolated process group, including after parent exit.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError:
            if process.poll() is None:
                raise
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                # Darwin can retain an empty, unreapable orphan group briefly.
                if process.poll() is None:
                    raise
            process.wait(timeout=5)
        process.stdout.close()


def build(command, budget=5400, delay=5):
    deadline = time.monotonic() + budget
    for attempt in range(2):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print('Image source recovery budget exhausted', file=sys.stderr)
            return 124
        # Each attempt owns these intermediate outputs. Never let output left
        # by a failed download satisfy the archive checks after a retry.
        for name in OUTPUTS:
            Path(name).unlink(missing_ok=True)
        try:
            status, log = invoke(command, remaining)
        except subprocess.TimeoutExpired:
            print('Image build exceeded its bounded budget', file=sys.stderr)
            return 124
        if status == 0:
            return 0
        if attempt or not retryable(log):
            return status
        print('Transient image source failure; retrying once with clean outputs', flush=True)
        time.sleep(min(delay, max(0, deadline-time.monotonic())))
    return status


if __name__ == '__main__':
    if len(sys.argv) < 3 or sys.argv[1] != '--':
        raise SystemExit('Usage: build_image_retry.py -- builder [arguments]')
    raise SystemExit(build(sys.argv[2:]))
