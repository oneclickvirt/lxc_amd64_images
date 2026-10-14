"""Publish a validated snapshot without overwriting concurrent maintenance."""
import argparse
import json
from pathlib import Path
import subprocess
import time

from image_catalog import validate as validate_catalog
from refresh_image_sources import validate as validate_definitions


def publish(root, branch):
    deadline = time.monotonic() + 240

    def git(*arguments, check=True):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('snapshot push budget exhausted')
        result = subprocess.run(['git', *arguments], cwd=root, capture_output=True,
                                text=True, timeout=min(60, remaining), check=False)
        if check and result.returncode:
            raise RuntimeError('snapshot Git operation failed: '+arguments[0])
        return result

    def validate():
        validate_definitions(root / 'images_yaml')
        validate_catalog(json.loads((root / '.github/image-catalog.json').read_text()))

    git('check-ref-format', 'refs/heads/'+branch)
    validate()
    for attempt in range(3):
        result = git('push', 'origin', 'HEAD:refs/heads/'+branch, check=False)
        if result.returncode == 0:
            print('Validated image source snapshot published')
            return
        if attempt == 2:
            raise RuntimeError('snapshot push retry budget exhausted')
        git('fetch', '--no-tags', 'origin', branch)
        # A push can reach GitHub before its response is lost. Do not create
        # another commit or overwrite later changes when it already arrived.
        if git('merge-base', '--is-ancestor', 'HEAD', 'FETCH_HEAD', check=False).returncode == 0:
            git('merge', '--ff-only', 'FETCH_HEAD')
            validate()
            print('Validated image source snapshot already published')
            return
        result = git('rebase', 'FETCH_HEAD', check=False)
        if result.returncode:
            git('rebase', '--abort', check=False)
            raise RuntimeError('concurrent source changes conflict; snapshot was not published')
        validate()
        print('Concurrent maintenance retained; retrying the revalidated source snapshot')
    raise RuntimeError('snapshot publication did not complete')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--branch', required=True)
    args = parser.parse_args()
    publish(Path.cwd(), args.branch)
