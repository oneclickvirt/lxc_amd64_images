"""Apply compatibility fixes after every upstream definition refresh."""
from pathlib import Path
from append_image_actions import serialize, normalize_el_boot
from verify_image_definitions import verify

NATIVE_IMAGE_ARCHIVES = False


def rpm_vm_compat(document, distro):
    """Keep EL firmware, BLS entries and the actual root partition in sync."""
    sets = document.setdefault('packages', {}).setdefault('sets', [])
    for entry in sets:
        if 'architectures' in entry:
            entry['architectures'] = ['aarch64' if arch == 'aaarch64' else arch
                                      for arch in entry['architectures']]
        entry['packages'] = ['grub2-efi-aa64' if package == 'grub2-efi-aarch64' else package
                             for package in entry.get('packages', [])]
    required = {'packages': ['grub2-tools', 'grubby'], 'action': 'install', 'types': ['vm']}
    if required not in sets:
        sets.append(required)
    # CentOS's upstream ARM selector omits EL9/EL10 entirely.
    if distro == 'centos':
        required = {'packages': ['grub2-efi-aa64'], 'action': 'install',
                    'types': ['vm'], 'architectures': ['aarch64'],
                    'releases': ['9-Stream', '10-Stream']}
        if required not in sets:
            sets.append(required)
    actions = document.setdefault('actions', [])
    rootvar = ('LXD_IMAGEBUILDER_ROOT_UUID' if any('LXD_IMAGEBUILDER_ROOT_UUID' in a['action']
                                                for a in actions) else 'DISTROBUILDER_ROOT_UUID')
    # These images have EFI + one root partition; /boot is on that root.
    # RPM assumes a separate /boot in both the firmware prefix and BLS paths.
    action = r"""#!/bin/sh
set -eu
# hosted-rpm-efi-forwarder
guest_root=${DISTROBUILDER_ROOT_UUID}
case "$guest_root" in UUID=*) guest_uuid=${guest_root#UUID=};; *) echo 'Expected UUID root device' >&2; exit 1;; esac
test -n "$guest_uuid"
mkdir -p /boot/grub2 /boot/loader/entries
if [ ! -s /boot/grub2/grub.cfg ]; then
  test -s /boot/efi/EFI/VENDOR/grub.cfg
  cp /boot/efi/EFI/VENDOR/grub.cfg /boot/grub2/grub.cfg
fi
test -s /boot/grub2/grub.cfg
entries=0
for entry in /boot/loader/entries/*.conf; do
  [ -f "$entry" ] || continue
  # RPM may record the builder host's mount prefix in a BLS entry.
  # Resolve kernel/initramfs basenames against the guest's actual /boot;
  # the existence gate below still rejects missing or unexpected images.
  awk '
    $1 == "linux" || $1 == "initrd" {
      for (i=2; i<=NF; i++) {
        name=$i; sub(/^.*\//, "", name)
        if (name ~ /^(vmlinuz-|initramfs-)/) $i="/boot/" name
      }
    }
    { print }
  ' "$entry" > "$entry.hosted"
  cat "$entry.hosted" > "$entry"
  rm "$entry.hosted"
  for image_path in $(awk '$1 == "linux" || $1 == "initrd" {for (i=2; i<=NF; i++) print $i}' "$entry"); do
    test -s "$image_path" || { echo "Missing BLS boot image: $image_path" >&2; exit 1; }
  done
  entries=$((entries + 1))
done
if grep -q 'blscfg' /boot/grub2/grub.cfg; then
  test "$entries" -gt 0
  if [ ! -s /boot/grub2/grubenv ]; then grub2-editenv /boot/grub2/grubenv create; fi
  grub2-editenv /boot/grub2/grubenv set blsdir=/boot/loader/entries
  grub2-editenv /boot/grub2/grubenv set "kernelopts=root=$guest_root ro console=tty1 console=ttyS0 console=ttyAMA0"
fi
for vendor in VENDOR BOOT; do
  mkdir -p "/boot/efi/EFI/$vendor"
  cat > "/boot/efi/EFI/$vendor/grub.cfg" <<EOF
search --no-floppy --fs-uuid --set=dev $guest_uuid
set prefix=(\$dev)/boot/grub2
export prefix
configfile \$prefix/grub.cfg
EOF
done
""".replace('DISTROBUILDER_ROOT_UUID', rootvar).replace('VENDOR', {
        'almalinux': 'almalinux', 'centos': 'centos', 'rockylinux': 'rocky'}[distro])
    hook = {'trigger': 'post-files', 'types': ['vm'],
            'releases': ['9-Stream', '10-Stream'] if distro == 'centos' else ['9', '10'],
            'action': action}
    for index, entry in enumerate(actions):
        if 'hosted-rpm-efi-forwarder' in entry['action']:
            actions[index] = hook
            break
    else:
        actions.append(hook)


def normalize(root):
    path = root / 'images_yaml/debian.yaml'
    document = verify(path.read_text())
    # Cloud generators remove build-time host keys. Debian's ssh.service
    # tests the configuration before it generates keys, so regenerate at
    # each first boot before that test without shipping shared host keys.
    ssh_hook = {'trigger': 'post-files', 'action': r"""#!/bin/sh
set -eu
# hosted-debian-ssh-hostkeys
mkdir -p /etc/systemd/system/ssh.service.d
printf '[Service]\nExecStartPre=\nExecStartPre=/usr/bin/ssh-keygen -A\nExecStartPre=/usr/sbin/sshd -t\n' > /etc/systemd/system/ssh.service.d/10-host-keys.conf
rm -f /etc/ssh/sshd_not_to_be_run
systemctl enable ssh.service
"""}
    if ssh_hook not in document.setdefault('actions', []):
        document['actions'].append(ssh_hook)
    path.write_text(serialize(document))

    path = root / 'images_yaml/fedora.yaml'
    document = verify(path.read_text())
    # fedora-http expects Koji's /packages tree, not the release ISO directory.
    document['source']['url'] = 'https://kojipkgs.fedoraproject.org'
    for entry in document.get('actions', []):
        # Current Fedora bootstrap rootfs does not contain this tool until
        # the systemd package transaction has completed.
        if entry['trigger'] == 'post-unpack' and 'systemd-machine-id-setup' in entry['action']:
            entry['trigger'] = 'post-packages'
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
    for entry in sets:
        if ('app-admin/syslog-ng' in entry.get('packages', [])
                and entry.get('variants') == ['openrc']):
            # The cloud variant uses the same OpenRC boot hook.
            entry['variants'] = ['openrc', 'cloud']
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
        # Alma's BaseOS packages use aa64 for EFI on ARM in EL8/EL9/EL10.
        entry['packages'] = ['grub2-efi-aa64' if package == 'grub2-efi-aarch64' else package
                             for package in entry.get('packages', [])]
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
    # Upstream removed vim-minimal, so legacy text insertion no longer adds
    # the default variant's SSH server or certificate-verifying HTTP client.
    sets = document.setdefault('packages', {}).setdefault('sets', [])
    existing = {package for entry in sets if entry.get('action') == 'install'
                and not any(entry.get(key) for key in ('types', 'variants', 'releases', 'architectures'))
                for package in entry.get('packages', [])}
    missing = [package for package in ('openssh-server', 'curl', 'ca-certificates')
               if package not in existing]
    if missing:
        sets.append({'packages': missing, 'action': 'install'})
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
systemctl enable sshd
"""}
    actions = document.setdefault('actions', [])
    for entry in actions:
        # The local stage renders DHCP configuration before networkd starts.
        # Enabling only cloud-init.service leaves Leap 16's NIC unmanaged.
        entry['action'] = entry['action'].replace(
            'systemctl enable cloud-init.service cloud-config.service cloud-final.service',
            'systemctl enable cloud-init-local.service cloud-init.service cloud-config.service cloud-final.service')
    for index, entry in enumerate(actions):
        if 'hosted-suse-ssh-defaults' in entry['action']:
            actions[index] = ssh_hook
            break
    else:
        actions.append(ssh_hook)
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
        if path.stem in ('almalinux', 'centos', 'rockylinux'):
            normalize_el_boot(path)
        document = verify(path.read_text())
        if path.stem == 'openeuler':
            # Verified against the vendor's current aarch64 RPM catalog.
            for entry in document.get('packages', {}).get('sets', []):
                entry['packages'] = ['grub2-efi-aa64' if p == 'grub2-efi-aarch64' else p
                                     for p in entry.get('packages', [])]
        if path.stem in ('almalinux', 'centos', 'rockylinux', 'fedora', 'openeuler'):
            # Current kernel-core packages can keep their bootable image in
            # /usr/lib/modules, while the VM hooks expect it under /boot.
            kernel_hook = {'trigger': 'post-packages', 'types': ['vm'], 'action': """#!/bin/sh
set -eu
# hosted-rpm-kernel-image
mkdir -p /boot
for modules in /usr/lib/modules/* /lib/modules/*; do
  [ -d "$modules" ] || continue
  version=${modules##*/}
  if [ -s "$modules/vmlinuz" ] && [ ! -s "/boot/vmlinuz-$version" ]; then
    cp "$modules/vmlinuz" "/boot/vmlinuz-$version"
  fi
done
"""}
            if kernel_hook not in document.setdefault('actions', []):
                document['actions'].append(kernel_hook)
        if path.stem in ('almalinux', 'centos', 'rockylinux'):
            rpm_vm_compat(document, path.stem)
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
    /run/*|../run/*|/var/run/*|../var/run/*)
      rm /etc/resolv.conf
      touch /etc/resolv.conf
      ;;
  esac
fi
"""}
        actions = document.setdefault('actions', [])
        if NATIVE_IMAGE_ARCHIVES and path.stem == 'opensuse':
            # Native SUSE archives rely on netconfig/resolved's live symlink.
            # Raw LXC consumers instead provide a resolver file via templates.
            actions[:] = [entry for entry in actions
                          if 'hosted-consumer-dns-file' not in entry['action']]
            path.write_text(serialize(document))
            continue
        for index, entry in enumerate(actions):
            if 'hosted-consumer-dns-file' in entry['action']:
                actions[index] = dns_hook
                break
        else:
            actions.append(dns_hook)
        path.write_text(serialize(document))
