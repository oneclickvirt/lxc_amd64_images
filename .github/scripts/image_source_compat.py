"""Apply compatibility fixes after every upstream definition refresh."""
from pathlib import Path
from append_image_actions import serialize
from verify_image_definitions import verify


def normalize(root):
    path = root / 'images_yaml/fedora.yaml'
    document = verify(path.read_text())
    # fedora-http expects Koji's /packages tree, not the release ISO directory.
    document['source']['url'] = 'https://kojipkgs.fedoraproject.org'
    path.write_text(serialize(document))

    path = root / 'images_yaml/openwrt.yaml'
    document = verify(path.read_text())
    # Upstream APK definitions no longer have the old '- sudo' insertion anchor.
    sets = document.setdefault('packages', {}).setdefault('sets', [])
    existing = {p for s in sets if s.get('action') == 'install' and not s.get('types')
                for p in s.get('packages', [])}
    missing = [p for p in ['curl', 'ca-bundle'] if p not in existing]
    if missing:
        sets.append({'packages': missing, 'action': 'install'})
    path.write_text(serialize(document))

    path = root / 'images_yaml/archlinux.yaml'
    document = verify(path.read_text())
    sets = document.setdefault('packages', {}).setdefault('sets', [])
    # ARM's rootfs is now minimal; retaining an upstream removal block also
    # removed openssh/libedit after installation. Keep runtime dependencies.
    for entry in sets:
        if entry.get('action') == 'remove':
            entry['packages'] = [p for p in entry['packages'] if p not in ['openssh', 'libedit']]
    sets[:] = [s for s in sets if s.get('packages')]
    if not any('openssh' in s['packages'] and s.get('action')=='install' and not s.get('architectures') for s in sets):
        sets.append({'packages': ['openssh'], 'action': 'install'})
    # Regional official mirrors allow pacman to recover from a stalled CDN
    # endpoint without changing package signature verification.
    mirror_hook = {'trigger': 'post-unpack', 'architectures': ['aarch64'], 'action': """#!/bin/sh
set -eu
# hosted-arm-mirror-fallback
cat > /etc/pacman.d/mirrorlist <<'MIRRORS'
Server = https://ca.us.mirror.archlinuxarm.org/$arch/$repo
Server = https://de3.mirror.archlinuxarm.org/$arch/$repo
MIRRORS
"""}
    actions = document.setdefault('actions', [])
    if mirror_hook not in actions:
        # Configure mirrors before the upstream pacman-keyring bootstrap hook.
        actions.insert(0, mirror_hook)
    path.write_text(serialize(document))

    path = root / 'images_yaml/gentoo.yaml'
    document = verify(path.read_text())
    # The old sudo anchor is now app-admin/sudo. Install runtime capabilities
    # independently of textual anchors and enable the selected init system.
    sets = document.setdefault('packages', {}).setdefault('sets', [])
    existing = {p for s in sets if s.get('action') == 'install' and not s.get('types')
                for p in s.get('packages', [])}
    missing = [p for p in ['net-misc/openssh', 'net-misc/curl', 'app-misc/ca-certificates'] if p not in existing]
    if missing:
        sets.append({'packages': missing, 'action': 'install'})
    for entry in document.get('actions', []):
        if 'sshd_config' in entry['action']:
            entry['variants'] = ['cloud', 'openrc', 'systemd']
    action = {'trigger': 'post-files', 'action': """#!/bin/sh
set -eu
command -v sshd >/dev/null
ssh-keygen -A
if command -v rc-update >/dev/null 2>&1; then
  rc-update add sshd default
elif command -v systemctl >/dev/null 2>&1; then
  systemctl enable sshd
else
  echo 'Unsupported Gentoo init system' >&2
  exit 1
fi
"""}
    if action not in document['actions']:
        document['actions'].append(action)
    path.write_text(serialize(document))

    path = root / 'images_yaml/almalinux.yaml'
    document = verify(path.read_text())
    # Upstream's aaarch64 typo silently omitted grub2-efi-aarch64 for ARM VMs.
    for entry in document.get('packages', {}).get('sets', []):
        if 'architectures' in entry:
            entry['architectures'] = ['aarch64' if arch == 'aaarch64' else arch
                                      for arch in entry['architectures']]
    for entry in document.get('actions', []):
        if 'hosted-compatible-bls' in entry['action']:
            entry['action'] = entry['action'].replace('\n  grub2-mkconfig -o "${target}"\nfi', '\nfi')
        if 'Track down the kernel' not in entry['action'] or 'hosted-el10-kernel' in entry['action']:
            continue
        before = 'kernel_path=$(find /boot -name "vmlinuz-${kver}" || true)'
        if before not in entry['action']:
            raise ValueError('unexpected EL10 kernel discovery hook')
        replacement = """# hosted-el10-kernel: kernel-core now keeps the RPM image under /usr/lib/modules.
if [ ! -s "/boot/vmlinuz-${kver}" ]; then
  for candidate in "/usr/lib/modules/${kver}/vmlinuz" "/lib/modules/${kver}/vmlinuz"; do
    if [ -s "$candidate" ]; then
      cp "$candidate" "/boot/vmlinuz-${kver}"
      break
    fi
  done
fi
kernel_path=$(find /boot -name "vmlinuz-${kver}" || true)"""
        entry['action'] = entry['action'].replace(before, replacement)
        # ARM guests use PL011 serial; retain x86's ttyS0 too.
        entry['action'] = entry['action'].replace('console=tty1 console=ttyS0', 'console=tty1 console=ttyS0 console=ttyAMA0')
    path.write_text(serialize(document))

    path = root / 'images_yaml/opensuse.yaml'
    document = verify(path.read_text())
    # New SUSE packages keep vendor SSH defaults under /usr/etc. Install the
    # mutable config before repository customization hooks edit it.
    ssh_hook = {'trigger': 'post-packages', 'action': """#!/bin/sh
set -eu
# hosted-suse-ssh-defaults
if [ ! -s /etc/ssh/sshd_config ] && [ -s /usr/etc/ssh/sshd_config ]; then
  mkdir -p /etc/ssh
  cp /usr/etc/ssh/sshd_config /etc/ssh/sshd_config
fi
mkdir -p /etc/systemd/system/sshd.service.d
printf '[Service]\\nExecStartPre=/usr/bin/ssh-keygen -A\\n' > /etc/systemd/system/sshd.service.d/10-host-keys.conf
"""}
    if ssh_hook not in document.setdefault('actions', []):
        document['actions'].append(ssh_hook)
    path.write_text(serialize(document))

    path = root / 'images_yaml/oracle.yaml'
    document = verify(path.read_text())
    # Oracle's ISO rootfs retains Anaconda's installer default.target. SSH
    # can be enabled yet never started because multi-user.target is absent
    # from that boot transaction. Select the normal installed-system target.
    target_hook = {'trigger': 'post-packages', 'action': """#!/bin/sh
set -eu
# hosted-oracle-runtime-target
systemctl set-default multi-user.target
"""}
    if target_hook not in document.setdefault('actions', []):
        document['actions'].append(target_hook)
    path.write_text(serialize(document))

    path = root / 'images_yaml/centos.yaml'
    document = verify(path.read_text())
    stale_mirror = 'https://mirror1.hs-esslingen.de/pub/Mirrors/centos-stream/'
    canonical_mirror = 'https://mirror.stream.centos.org/'

    def replace_mirror(value):
        if isinstance(value, str):
            return value.replace(stale_mirror, canonical_mirror)
        if isinstance(value, list):
            return [replace_mirror(item) for item in value]
        if isinstance(value, dict):
            return {key: replace_mirror(item) for key, item in value.items()}
        return value

    for entry in document.get('actions', []):
        entry['action'] = replace_mirror(entry['action'])
    packages = document.setdefault('packages', {})
    repositories = packages.get('repositories', [])
    packages['repositories'] = replace_mirror(repositories)
    path.write_text(serialize(document))

    for path in (root / 'images_yaml').glob('*.yaml'):
        document = verify(path.read_text())
        for entry in document.get('actions', []):
            entry['action'] = entry['action'].replace('PubkeyAuthentication no', 'PubkeyAuthentication yes')
        # /run is recreated at boot. Dangling resolvers in SUSE and older
        # Ubuntu images prevent the consumer from writing a DNS template
        # before start. Keep DHCP policy and a writable resolver target.
        dns_hook = {'trigger': 'post-files', 'types': ['container'], 'action': """#!/bin/sh
set -eu
# hosted-consumer-dns-file
if [ -L /etc/resolv.conf ]; then
  case "$(readlink /etc/resolv.conf)" in
    /run/*|../run/*)
      rm /etc/resolv.conf
      touch /etc/resolv.conf
      ;;
  esac
fi
"""}
        if dns_hook not in document.setdefault('actions', []):
            document['actions'].append(dns_hook)
        path.write_text(serialize(document))
