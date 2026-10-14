"""Stage upstream definition updates and release indexes; retain a valid fallback."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

import yaml

from append_image_actions import normalize_oracle, normalize_el10, normalize_el_boot
from image_source_compat import normalize
from image_catalog import refresh_catalog
from verify_image_definitions import verify

REPOSITORIES = {"lxc_amd64_images", "lxc_arm_images", "incus_images", "lxd_images"}
DISTROS = set("debian ubuntu kali centos almalinux rockylinux oracle archlinux fedora alpine openwrt opensuse openeuler gentoo".split())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        return None


def api_json(path, deadline):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "oneclickvirt-image-refresh"}
    token = os.environ.get("GH_TOKEN", "")
    if token:
        headers["Authorization"] = "Bearer " + token
    for attempt in range(3):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("source refresh budget exhausted")
        request = urllib.request.Request("https://api.github.com" + path, headers=headers)
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=min(30, remaining)) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code not in {408, 429, 500, 502, 503, 504} or attempt == 2:
                raise RuntimeError("source API unavailable") from None
        except (TimeoutError, urllib.error.URLError):
            if attempt == 2:
                raise RuntimeError("source transport unavailable") from None
        time.sleep(min(2 ** attempt, max(0, deadline - time.monotonic())))
    raise RuntimeError("source request did not complete")


def validate(directory):
    paths = sorted(directory.glob("*.yaml"))
    if {path.stem for path in paths} != DISTROS:
        raise ValueError("image definition catalog is incomplete")
    for path in paths:
        verify(path.read_text())
    return len(paths)


def release_indexes(repo, deadline):
    releases = []
    for page in range(1, 21):
        batch = api_json(f"/repos/oneclickvirt/{repo}/releases?per_page=100&page={page}", deadline)
        releases.extend(batch)
        if len(batch) < 100:
            break
    else:
        raise ValueError("release catalog exceeds pagination limit")
    pattern = re.compile(r"^([a-z0-9]+)_([A-Za-z0-9_.-]+)_([A-Za-z0-9_.-]+)_(x86_64|amd64|arm64|aarch64)_([A-Za-z0-9_.-]+)\.(tar\.xz|zip)$")
    groups = {"x86_64": set(), "arm64": set()}
    extension = "tar.xz" if repo.startswith("lxc_") else "zip"
    for release in releases:
        if release["draft"] or release["prerelease"] or release["tag_name"] not in DISTROS:
            continue
        assets = release["assets"]
        if len(assets) >= 100:
            assets = []
            for page in range(1, 21):
                batch = api_json(f"/repos/oneclickvirt/{repo}/releases/{release['id']}/assets?per_page=100&page={page}", deadline)
                assets.extend(batch)
                if len(batch) < 100:
                    break
            else:
                raise ValueError("release assets exceed pagination limit")
        for asset in assets:
            match = pattern.fullmatch(asset["name"])
            if not match or match[1] != release["tag_name"] or match[6] != extension:
                continue
            if asset.get("state") != "uploaded" or not asset.get("size"):
                continue
            group = "x86_64" if match[4] in {"x86_64", "amd64"} else "arm64"
            groups[group].add(asset["name"])
    if repo == "lxc_amd64_images":
        values = {"all_images.txt": groups["x86_64"]}
    elif repo == "lxc_arm_images":
        values = {"all_images.txt": groups["arm64"]}
    else:
        values = {"x86_64_all_images.txt": groups["x86_64"], "arm64_all_images.txt": groups["arm64"]}
    if any(not names for names in values.values()):
        raise ValueError("refusing to replace an image index with an empty catalog")
    return {name: "\n".join(sorted(names)) + "\n" for name, names in values.items()}


def promote(root, stage, names):
    originals = {name: (root / name).read_bytes() if (root / name).exists() else None for name in names}
    installed = []
    try:
        for name in names:
            destination = root / name
            source = stage / name
            if originals[name] == source.read_bytes():
                continue
            # Stage is on the same filesystem as the repository.
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.replace(destination)
            installed.append(name)
    except BaseException:
        for name in installed:
            if originals[name] is None:
                (root / name).unlink()
            else:
                (root / name).write_bytes(originals[name])
        raise
    return len(installed)


def prepare(root, stage, repo, deadline):
    shutil.copytree(root / "images_yaml", stage / "images_yaml")
    for name in ["bash_insert_content.text", "sh_insert_content.text"]:
        shutil.copy2(root / name, stage / name)
    scripts = stage / ".github/scripts"
    scripts.mkdir(parents=True)
    for name in ["append_image_actions.py", "verify_image_definitions.py", "ci_network.sh", "image_catalog.py", "image_source_compat.py"]:
        shutil.copy2(root / ".github/scripts" / name, scripts / name)
    legacy = (root / ".github/scripts/refresh_image_definitions.sh").read_text()
    source_commit = api_json("/repos/lxc/lxc-ci/commits/main", deadline)["sha"]
    if repo != "lxd_images":
        if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
            raise ValueError("invalid upstream definition commit")
        legacy = legacy.replace("/lxc/lxc-ci/main/", f"/lxc/lxc-ci/{source_commit}/")
    (stage / "clone_modify_yaml.sh").write_text(legacy)
    environment = dict(os.environ, GITHUB_WORKSPACE=str(stage), CI_IMAGE_SCRIPT_ROOT=str(scripts), CI_IMAGE_PYTHON=sys.executable)
    process = subprocess.Popen(["bash", str(stage / "clone_modify_yaml.sh")], cwd=stage, env=environment,
                               start_new_session=True)
    try:
        code = process.wait(timeout=max(1, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        raise
    if code:
        raise subprocess.CalledProcessError(code, "isolated image definition generator")
    normalize_oracle(stage / "images_yaml/oracle.yaml")
    normalize_el10(stage / "images_yaml/almalinux.yaml")
    normalize_el_boot(stage / "images_yaml/almalinux.yaml")
    normalize(stage)
    refresh_catalog(stage, source_commit, deadline)
    validate(stage / "images_yaml")
    indexes = release_indexes(repo, deadline)
    for name, content in indexes.items():
        (stage / name).write_text(content)
    names = ["images_yaml/" + path.name for path in sorted((stage / "images_yaml").iterdir()) if path.is_file()] + list(indexes) + [".github/image-catalog.json"]
    for name in names:
        (stage / name).chmod(0o644)
    return names


def refresh(root, repo, prepare_stage=prepare):
    count = validate(root / "images_yaml")
    # Baseline validation is outside recovery: a broken fallback is never success.
    with tempfile.TemporaryDirectory(prefix=".image-refresh-", dir=root) as temporary:
        stage = Path(temporary)
        try:
            names = prepare_stage(root, stage, repo, time.monotonic() + 600)
            changed = promote(root, stage, names)
        except (OSError, RuntimeError, ValueError, yaml.YAMLError, subprocess.SubprocessError) as error:
            return {"status": "deferred", "definitions": count, "changed_files": 0,
                    "reason": type(error).__name__, "used_validated_fallback": True}
    return {"status": "updated", "definitions": count, "changed_files": changed, "used_validated_fallback": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", choices=sorted(REPOSITORIES), required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    result = refresh(root, args.repository)
    result["checked_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    print(json.dumps(result, sort_keys=True))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as stream:
            stream.write("### Image source refresh\n\n")
            stream.write(f"Status: **{result['status']}**. Valid definitions: {result['definitions']}. Changed files: {result['changed_files']}.\n\n")
            if result["used_validated_fallback"]:
                stream.write("The upstream refresh was deferred; existing validated definitions and image indexes were retained. No new source snapshot was accepted.\n")
    if result["used_validated_fallback"]:
        print("::notice::Source refresh deferred; existing validated definitions and indexes retained.")


if __name__ == "__main__":
    main()
