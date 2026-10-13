"""Append repository customization hooks as YAML actions, never by line count."""
from pathlib import Path
import sys

import yaml

from verify_image_definitions import UniqueKeyLoader, verify


class DefinitionDumper(yaml.SafeDumper):
    pass


def string_value(dumper, value):
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|" if "\n" in value else None)


DefinitionDumper.add_representer(str, string_value)


def serialize(document):
    content = yaml.dump(document, Dumper=DefinitionDumper, sort_keys=False, allow_unicode=True)
    verify(content)
    return content


def append(path, hook):
    document = verify(path.read_text())
    additions = yaml.load(hook.read_text(), Loader=UniqueKeyLoader)
    if not isinstance(additions, list) or not additions:
        raise ValueError("customization hook must be a nonempty actions list")
    for entry in additions:
        if not isinstance(entry, dict) or not isinstance(entry.get("trigger"), str) or not isinstance(entry.get("action"), str):
            raise ValueError("invalid customization action")
    actions = document.setdefault("actions", [])
    for entry in additions:
        if entry not in actions:
            actions.append(entry)
    path.write_text(serialize(document))


def normalize_oracle(path):
    document = verify(path.read_text())
    document["source"]["url"] = "https://yum.oracle.com/ISOS/OracleLinux"
    repositories = document.get("packages", {}).get("repositories", [])
    appstream = [entry for entry in repositories if entry.get("name") == "AppStream"]
    if len(appstream) != 1:
        raise ValueError("expected one Oracle AppStream repository")
    repository = appstream[0]
    repository.pop("variants", None)
    repository["url"] = repository["url"].replace("http://yum.oracle.com/", "https://yum.oracle.com/")
    if "gpgcheck=1" not in repository["url"] or "gpgcheck=0" in repository["url"]:
        raise ValueError("Oracle AppStream must retain GPG verification")
    path.write_text(serialize(document))


if __name__ == "__main__":
    append(Path(sys.argv[1]), Path(sys.argv[2]))
