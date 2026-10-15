"""Remove builder SSH identities and generate fresh host keys on first boot."""
import re


KEY_PATH = re.compile(r'^(?:etc/ssh/ssh_host_[^/]+_key(?:\.pub|-cert\.pub)?|etc/dropbear/dropbear_[^/]+_host_key)$')
UNIT = '''[Unit]
Description=Generate this instance's missing SSH host keys
After=local-fs.target
Before=ssh.service sshd.service
[Service]
Type=oneshot
ExecStart=KEYGEN -A
RemainAfterExit=yes
'''
DEPENDENCY = '''[Unit]
Requires=image-ssh-hostkeys.service
After=image-ssh-hostkeys.service
'''


def runtime_files(names):
    """Add dependencies without replacing the distribution's SSH service."""
    names = set(names)
    services = [service for service in ('ssh', 'sshd') if any(
        f'{prefix}/{service}.service' in names
        for prefix in ('usr/lib/systemd/system', 'lib/systemd/system', 'etc/systemd/system'))]
    if not services:
        return {}
    keygen = next(('/' + name for name in ('usr/bin/ssh-keygen', 'bin/ssh-keygen') if name in names), None)
    if keygen is None:
        raise ValueError('SSH systemd service has no key generator')
    files = {'etc/systemd/system/image-ssh-hostkeys.service': UNIT.replace('KEYGEN', keygen)}
    files.update({f'etc/systemd/system/{service}.service.d/50-image-hostkeys.conf': DEPENDENCY
                  for service in services})
    return files


BUILD_HOOK = r'''#!/bin/sh
set -eu
# hosted-instance-ssh-identity
# Never ship an identity created by the vendor package installer or a hook.
rm -f /etc/ssh/ssh_host_*_key /etc/ssh/ssh_host_*_key.pub /etc/ssh/ssh_host_*_key-cert.pub
rm -f /etc/dropbear/dropbear_*_host_key
# OpenRC and procd SSH services already generate absent host keys. systemd
# packages differ: run keygen before the vendor service's configuration test.
services=''
for service in ssh sshd; do
  if [ -f "/usr/lib/systemd/system/$service.service" ] || [ -f "/lib/systemd/system/$service.service" ] || [ -f "/etc/systemd/system/$service.service" ]; then
    services="$services $service"
  fi
done
if [ -n "$services" ]; then
  keygen=$(command -v ssh-keygen)
  test -x "$keygen"
  mkdir -p /etc/systemd/system
  cat > /etc/systemd/system/image-ssh-hostkeys.service <<UNIT
[Unit]
Description=Generate this instance's missing SSH host keys
After=local-fs.target
Before=ssh.service sshd.service
[Service]
Type=oneshot
ExecStart=$keygen -A
RemainAfterExit=yes
UNIT
  for service in $services; do
    mkdir -p "/etc/systemd/system/$service.service.d"
    cat > "/etc/systemd/system/$service.service.d/50-image-hostkeys.conf" <<'UNIT'
[Unit]
Requires=image-ssh-hostkeys.service
After=image-ssh-hostkeys.service
UNIT
  done
fi
'''
