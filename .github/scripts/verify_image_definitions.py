"""Reject broken or ambiguous image definitions before provisioning a runner."""
import argparse
from pathlib import Path
import re

import yaml


class UniqueKeyLoader(yaml.SafeLoader):
    """Do not silently discard an earlier actions/packages mapping."""


def unique_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise yaml.constructor.ConstructorError(
                "duplicate mapping key", node.start_mark, str(key), key_node.start_mark
            )
        # Image builders parse file permissions as an octal string. YAML 1.1
        # otherwise turns 0600 into integer 384, which then corrupts the next
        # upstream refresh when dumped as decimal text.
        if key == "mode" and isinstance(value_node, yaml.ScalarNode):
            result[key] = loader.construct_scalar(value_node)
        else:
            result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping
)


def verify(content):
    document = yaml.load(content, Loader=UniqueKeyLoader)
    if not isinstance(document, dict):
        raise ValueError("image definition must be a mapping")
    for key in ("image", "source"):
        if not isinstance(document.get(key), dict):
            raise ValueError(f"{key} must be a mapping")
    if not document["source"].get("downloader"):
        raise ValueError("source.downloader is required")
    for key in ("actions", "files"):
        entries = document.get(key, [])
        if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
            raise ValueError(f"{key} must be a list of mappings")
    for entry in document.get("actions", []):
        if not isinstance(entry.get("trigger"), str) or not isinstance(entry.get("action"), str):
            raise ValueError("each action requires a trigger and script")
    for entry in document.get("files", []):
        if "mode" in entry and (not isinstance(entry["mode"], str)
                                or not re.fullmatch(r"[0-7]{1,4}", entry["mode"])):
            raise ValueError("file mode must be an octal permission string")
    if "mappings" in document and not isinstance(document["mappings"], dict):
        raise ValueError("mappings must be a mapping")
    if "packages" in document:
        packages = document["packages"]
        if not isinstance(packages, dict) or not isinstance(packages.get("sets", []), list):
            raise ValueError("packages must contain a list of sets")
    return document


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", nargs="?", default="images_yaml")
    args = parser.parse_args()
    paths = sorted(Path(args.directory).glob("*.y*ml"))
    if not paths:
        raise SystemExit("No image definitions found")
    for path in paths:
        try:
            verify(path.read_text())
        except (ValueError, yaml.YAMLError) as exc:
            raise SystemExit(f"Invalid image definition {path}: {exc}") from None
    print(f"Validated {len(paths)} image definitions")


if __name__ == "__main__":
    main()
