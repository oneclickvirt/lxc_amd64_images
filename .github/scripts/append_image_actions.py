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


def normalize_el10(path):
    """EL10 removed dhclient; retain DHCP through NetworkManager's own client."""
    document = verify(path.read_text())
    sets = document.get('packages', {}).get('sets', [])
    for entry in list(sets):
        releases = [str(r) for r in entry.get('releases', [])]
        if 'dhclient' in entry.get('packages', []) and ('10' in releases or not releases):
            entry['packages'] = [package for package in entry['packages'] if package != 'dhclient']
            legacy_releases = [r for r in entry.get('releases', []) if str(r) != '10'] or (['8', '9'] if not releases else [])
            if legacy_releases:
                sets.append(dict(entry, packages=['dhclient'], releases=legacy_releases))
        if 'NetworkManager' in entry.get('packages', []) and entry.get('types') == ['container'] and '9' in releases and '10' not in releases:
            entry['releases'].append('10')
    sets[:] = [entry for entry in sets if entry.get('packages')]
    for entry in list(document.get('actions', [])):
        releases = [str(r) for r in entry.get('releases', [])]
        if ('dhcp=dhclient' not in entry['action'] or entry.get('types') != ['container']
                or (releases and not {'9', '10'}.intersection(releases))):
            continue
        legacy_releases = [r for r in entry.get('releases', []) if str(r) != '10']
        if not releases:
            legacy_releases = ['8', '9']
        if legacy_releases:
            entry['releases'] = legacy_releases
        else:
            document['actions'].remove(entry)
        additional = dict(entry, releases=['10'], action=entry['action'].replace('dhcp=dhclient','dhcp=internal'))
        if additional not in document['actions']:
            document['actions'].append(additional)
    path.write_text(serialize(document))


def normalize_el_boot(path):
    document = verify(path.read_text())
    for entry in document.get('actions', []):
        for vendor in ('almalinux', 'centos', 'rocky', 'fedora'):
            entry['action'] = entry['action'].replace(
                'target=/boot/efi/EFI/' + vendor + '/grub.cfg', 'target=/boot/grub2/grub.cfg')
        if 'hosted-compatible-bls' in entry['action']:
            entry['action'] = entry['action'].replace(
                'target=/boot/efi/EFI/almalinux/grub.cfg', 'target=/boot/grub2/grub.cfg')
            continue
        before = '    grubby --update-kernel=/boot/vmlinuz-${kver} --args="root=${DISTROBUILDER_ROOT_UUID} ro"'
        if 'grubby --update-kernel=/boot/vmlinuz-${kver}' not in entry['action']:
            continue
        action = entry['action']
        rootvar = 'LXD_IMAGEBUILDER_ROOT_UUID' if 'LXD_IMAGEBUILDER_ROOT_UUID' in action else 'DISTROBUILDER_ROOT_UUID'
        before = before.replace('DISTROBUILDER_ROOT_UUID', rootvar)
        # YAML block indentation is already stripped when parsing.
        before = before.strip()
        if action.count(before) != 1:
            raise ValueError('unexpected RPM boot entry hook')
        replacement = '# hosted-compatible-bls: retain upstream grubby and supply missing RPM boot metadata\nmkdir -p /boot/grub2 /boot/loader/entries\nif [ ! -f /boot/grub2/grubenv ]; then\n  grub2-editenv /boot/grub2/grubenv create\nfi\ntest -s "/boot/vmlinuz-${kver}"\nif ! grubby --update-kernel=/boot/vmlinuz-${kver} --args="root=${DISTROBUILDER_ROOT_UUID} ro"; then\n  printf \'title AlmaLinux\nversion %s\nlinux /vmlinuz-%s\ninitrd /initramfs-%s.img\noptions root=%s ro console=tty0 console=ttyS0 console=ttyAMA0\n\' "${kver}" "${kver}" "${kver}" "${DISTROBUILDER_ROOT_UUID}" > "/boot/loader/entries/hosted-${kver}.conf"\n  grubby --update-kernel=/boot/vmlinuz-${kver} --args="root=${DISTROBUILDER_ROOT_UUID} ro"\nfi'
        rendered = replacement.replace('DISTROBUILDER_ROOT_UUID', rootvar)
        rendered = rendered.replace(
            'if [ ! -f /boot/grub2/grubenv ]; then\n  grub2-editenv /boot/grub2/grubenv create\nfi',
            'if command -v grub2-editenv >/dev/null 2>&1 && [ ! -f /boot/grub2/grubenv ]; then\n  grub2-editenv /boot/grub2/grubenv create\nfi')
        rendered = rendered.replace(
            'test -s "/boot/vmlinuz-${kver}"',
            'kernel="/boot/vmlinuz-${kver}"\nif [ ! -s "$kernel" ]; then\n  for candidate in "/usr/lib/modules/${kver}/vmlinuz" "/lib/modules/${kver}/vmlinuz"; do\n    if [ -s "$candidate" ]; then cp "$candidate" "$kernel"; break; fi\n  done\nfi\nif [ ! -s "$kernel" ]; then echo "Kernel image $kernel not found" >&2; exit 1; fi')
        rendered = rendered.replace(
            '  grubby --update-kernel=/boot/vmlinuz-${kver} --args="root=${' + rootvar + '} ro"\nfi',
            'fi')
        action = action.replace(before, rendered)
        action = action.replace('target=/boot/efi/EFI/almalinux/grub.cfg', 'target=/boot/grub2/grub.cfg')
        entry['action'] = action
    path.write_text(serialize(document))


if __name__ == "__main__":
    append(Path(sys.argv[1]), Path(sys.argv[2]))
