"""Source failures must not overwrite validated definitions or release indexes."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import append_image_actions as hooks
import refresh_image_sources as refresh
from verify_image_definitions import verify


DEFINITION = "image:\n  distribution: fixture\nsource:\n  downloader: fixture\nactions: []\nmappings:\n  architecture_map: {}\n"


class ImageSourceRefreshTests(unittest.TestCase):
    def test_file_permissions_survive_yaml_refresh_without_decimal_conversion(self):
        for mode in ['0600', '0440', '0755', '644']:
            document = verify(DEFINITION + 'files:\n- path: /fixture\n  mode: ' + mode + '\n')
            self.assertEqual(document['files'][0]['mode'], mode)
            refreshed = hooks.serialize(document)
            self.assertEqual(verify(refreshed)['files'][0]['mode'], mode)
            self.assertEqual(hooks.serialize(verify(refreshed)), refreshed)

    def test_invalid_decimal_permissions_fail_before_build(self):
        for mode in ['384', '288', '493', 'not-a-mode']:
            with self.assertRaisesRegex(ValueError, 'octal permission'):
                verify(DEFINITION + 'files:\n- path: /fixture\n  mode: ' + mode + '\n')

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        definitions = self.root / "images_yaml"
        definitions.mkdir()
        for distro in refresh.DISTROS:
            (definitions / (distro + ".yaml")).write_text(DEFINITION)
        (self.root / "all_images.txt").write_text("previous-valid-index\n")

    def tearDown(self):
        self.directory.cleanup()

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def test_hooks_follow_actions_even_when_mappings_is_last(self):
        path = self.root / "images_yaml/openwrt.yaml"
        hook = self.root / "hook.text"
        hook.write_text('- trigger: post-packages\n  action: |\n    #!/bin/sh\n    echo fixture\n')
        hooks.append(path, hook)
        hooks.append(path, hook)
        document = verify(path.read_text())
        self.assertEqual(len(document["actions"]), 1)
        self.assertEqual(document["mappings"], {"architecture_map": {}})

    def test_oracle_normalization_retains_gpg_and_all_variants(self):
        path = self.root / "images_yaml/oracle.yaml"
        path.write_text(DEFINITION + 'packages:\n  repositories:\n  - name: AppStream\n    variants: [cloud]\n    url: |\n      baseurl=http://yum.oracle.com/repo/OracleLinux/OL{{ image.release }}/appstream/$basearch/\n      enabled=1\n      gpgcheck=1\n')
        hooks.normalize_oracle(path)
        document = verify(path.read_text())
        repository = document["packages"]["repositories"][0]
        self.assertNotIn("variants", repository)
        self.assertIn("https://yum.oracle.com/", repository["url"])
        self.assertIn("gpgcheck=1", repository["url"])
        self.assertEqual(document["source"]["url"], "https://yum.oracle.com/ISOS/OracleLinux")
        original = path.read_bytes()
        path.write_bytes(original.replace(b"gpgcheck=1", b"gpgcheck=0"))
        rejected = path.read_bytes()
        with self.assertRaises(ValueError):
            hooks.normalize_oracle(path)
        self.assertEqual(path.read_bytes(), rejected)

    def test_el10_network_normalization_is_stable_and_preserves_el8_el9(self):
        path = self.root / 'images_yaml/almalinux.yaml'
        path.write_text(DEFINITION.replace('actions: []', 'actions:\n- trigger: post-files\n  types: [container]\n  releases: [9]\n  action: printf "dhcp=dhclient"') + 'packages:\n  sets:\n  - action: install\n    packages: [curl, dhclient]\n  - action: install\n    packages: [NetworkManager]\n    types: [container]\n    releases: [9]\n')
        hooks.normalize_el10(path)
        document = verify(path.read_text())
        for entry in document['packages']['sets']:
            if 'dhclient' in entry['packages']:
                self.assertEqual(set(map(str, entry['releases'])), {'8', '9'})
            if 'NetworkManager' in entry['packages']:
                self.assertIn('10', list(map(str, entry['releases'])))
        self.assertTrue(any('dhcp=internal' in e['action'] and e['releases'] == ['10'] for e in document['actions']))
        normalized = path.read_bytes()
        hooks.normalize_el10(path)
        self.assertEqual(path.read_bytes(), normalized)

    def test_el10_dhclient_normalization_covers_rocky_and_oracle_defaults(self):
        rocky = self.root / 'images_yaml/rockylinux.yaml'
        rocky_actions = chr(10).join([
            'actions:', '- trigger: post-files', '  types: [container]',
            "  action: 'printf dhcp=dhclient'",
        ])
        rocky_packages = chr(10).join([
            'packages:', '  sets:', '  - action: install', '    packages: [curl, dhclient]',
        ])
        rocky.write_text(DEFINITION.replace('actions: []', rocky_actions) + rocky_packages + chr(10))
        hooks.normalize_el10(rocky)
        rocky_doc = verify(rocky.read_text())
        self.assertNotIn('dhclient', next(s for s in rocky_doc['packages']['sets'] if 'curl' in s['packages'])['packages'])
        self.assertTrue(any(s['packages'] == ['dhclient'] and set(map(str, s['releases'])) == {'8', '9'}
                            for s in rocky_doc['packages']['sets']))
        actions = [a for a in rocky_doc['actions'] if 'dhcp=' in a['action']]
        self.assertEqual({tuple(map(str, a['releases'])) for a in actions}, {('8', '9'), ('10',)})
        self.assertTrue(any('dhcp=internal' in a['action'] and list(map(str, a['releases'])) == ['10'] for a in actions))

        oracle = self.root / 'images_yaml/oracle.yaml'
        oracle_packages = chr(10).join([
            'packages:', '  sets:', '  - action: install', '    packages: [curl, dhclient]',
        ])
        oracle.write_text(DEFINITION + oracle_packages + chr(10))
        hooks.normalize_el10(oracle)
        oracle_doc = verify(oracle.read_text())
        self.assertNotIn('dhclient', next(s for s in oracle_doc['packages']['sets'] if 'curl' in s['packages'])['packages'])
        self.assertTrue(any(s['packages'] == ['dhclient'] and set(map(str, s['releases'])) == {'8', '9'}
                            for s in oracle_doc['packages']['sets']))

    def test_arm_bootloader_selector_and_mirror_recovery_survive_refresh(self):
        import image_source_compat
        alma = self.root / 'images_yaml/almalinux.yaml'
        alma.write_text(DEFINITION + 'packages:\n  sets:\n  - action: install\n    packages: [grub2-efi-aarch64]\n    architectures: [aaarch64]\n    types: [vm]\n')
        arch = self.root / 'images_yaml/archlinux.yaml'
        arch.write_text(DEFINITION.replace('actions: []', 'actions:\n- trigger: post-unpack\n  action: pacman -Sy --needed --noconfirm archlinux-keyring'))
        image_source_compat.normalize(self.root)
        self.assertEqual(verify(alma.read_text())['packages']['sets'][0]['architectures'], ['aarch64'])
        actions = verify(arch.read_text())['actions']
        self.assertEqual(actions[0]['architectures'], ['aarch64'])
        self.assertIn('https://ca.us.mirror.archlinuxarm.org/$arch/$repo', actions[0]['action'])
        self.assertIn('https://de3.mirror.archlinuxarm.org/$arch/$repo', actions[0]['action'])
        self.assertNotIn('SigLevel', actions[0]['action'])
        self.assertTrue(actions[1]['action'].startswith('pacman'))
        before = self.snapshot()
        image_source_compat.normalize(self.root)
        self.assertEqual(before, self.snapshot())

    def test_oracle_installer_default_target_is_replaced_after_every_refresh(self):
        import image_source_compat
        image_source_compat.normalize(self.root)
        actions = verify((self.root / 'images_yaml/oracle.yaml').read_text())['actions']
        hook = next(a for a in actions if 'hosted-oracle-runtime-target' in a['action'])
        self.assertEqual(hook['trigger'], 'post-packages')
        self.assertIn('systemctl set-default multi-user.target', hook['action'])
        self.assertNotIn('variants', hook)
        before = self.snapshot()
        image_source_compat.normalize(self.root)
        self.assertEqual(before, self.snapshot())


    def test_suse_dns_template_target_and_vendor_ssh_defaults_survive_refresh(self):
        import image_source_compat
        image_source_compat.normalize(self.root)
        actions = verify((self.root / 'images_yaml/opensuse.yaml').read_text())['actions']
        ssh = next(a for a in actions if 'hosted-suse-ssh-defaults' in a['action'])
        dns = next(a for a in actions if 'hosted-consumer-dns-file' in a['action'])
        self.assertEqual(ssh['trigger'], 'post-packages')
        self.assertIn('cp /usr/etc/ssh/sshd_config /etc/ssh/sshd_config', ssh['action'])
        self.assertIn('ExecStartPre=/usr/bin/ssh-keygen -A', ssh['action'])
        self.assertEqual(dns['types'], ['container'])
        self.assertIn('touch /etc/resolv.conf', dns['action'])
        self.assertNotIn('NETCONFIG_DNS_POLICY', dns['action'])
        previous = self.snapshot()
        image_source_compat.normalize(self.root)
        self.assertEqual(previous, self.snapshot())

    def test_dangling_run_resolver_becomes_a_writable_consumer_target(self):
        import image_source_compat
        import subprocess
        image_source_compat.normalize(self.root)
        actions = verify((self.root / 'images_yaml/ubuntu.yaml').read_text())['actions']
        hook = next(a['action'] for a in actions if 'hosted-consumer-dns-file' in a['action'])
        directory = self.root / 'resolver-fixture'
        directory.mkdir()
        resolver = directory / 'resolv.conf'
        for target in ['/run/netconfig/resolv.conf', '../run/systemd/resolve/stub-resolv.conf']:
            resolver.unlink(missing_ok=True)
            resolver.symlink_to(target)
            subprocess.run(['sh', '-c', hook.replace('/etc/resolv.conf', str(resolver))], check=True, timeout=5)
            self.assertFalse(resolver.is_symlink())
            resolver.write_text('nameserver 10.0.0.1\n')
            subprocess.run(['sh', '-c', hook.replace('/etc/resolv.conf', str(resolver))], check=True, timeout=5)
            self.assertEqual(resolver.read_text(), 'nameserver 10.0.0.1\n')

    def test_vm_kernel_core_layout_recovers_missing_boot_image_and_preserves_existing(self):
        import image_source_compat
        import subprocess
        import re
        image_source_compat.normalize(self.root)
        actions = verify((self.root / 'images_yaml/centos.yaml').read_text())['actions']
        hook = next(a for a in actions if 'hosted-rpm-kernel-image' in a['action'])
        self.assertEqual(hook['types'], ['vm'])
        folder = self.root / 'kernel-fixture'
        (folder / 'usr/lib/modules/test-kernel').mkdir(parents=True)
        (folder / 'lib/modules').mkdir(parents=True)
        kernel = folder / 'usr/lib/modules/test-kernel/vmlinuz'
        kernel.write_bytes(b'vendor kernel fixture')
        command = re.sub(r'/usr/lib/modules/|/lib/modules/|/boot', lambda match: str(folder) + match.group(), hook['action'])
        subprocess.run(['sh', '-c', command], check=True, timeout=5)
        output = folder / 'boot/vmlinuz-test-kernel'
        self.assertEqual(output.read_bytes(), kernel.read_bytes())
        output.write_bytes(b'existing boot image')
        subprocess.run(['sh', '-c', command], check=True, timeout=5)
        self.assertEqual(output.read_bytes(), b'existing boot image')


    def test_upstream_compatibility_retains_signatures_and_is_idempotent(self):
        import image_source_compat
        fedora=self.root/'images_yaml/fedora.yaml'
        fedora.write_text(DEFINITION.replace('downloader: fixture','downloader: fedora-http\n  url: https://dl.fedoraproject.org/pub/fedora/linux/releases'))
        alma=self.root/'images_yaml/almalinux.yaml'
        alma.write_text(DEFINITION.replace('actions: []', 'actions:\n- trigger: post-files\n  releases: [10]\n  types: [vm]\n  action: |\n    # Track down the kernel\n    kernel_path=$(find /boot -name "vmlinuz-${kver}" || true)'))
        gentoo=self.root/'images_yaml/gentoo.yaml'
        gentoo.write_text(DEFINITION.replace('actions: []', 'actions: []')+'packages:\n  sets:\n  - action: install\n    packages: [app-admin/sudo]\n')
        centos_lines = [
            'actions:', '- trigger: post-unpack', '  action: |', '    cat <<EOF',
            '    baseurl=https://mirror1.hs-esslingen.de/pub/Mirrors/centos-stream/$stream/BaseOS/$basearch/os/',
            '    baseurl=https://mirror1.hs-esslingen.de/pub/Mirrors/centos-stream/$stream/AppStream/$basearch/os/',
            '    baseurl=https://mirror1.hs-esslingen.de/pub/Mirrors/centos-stream/SIGs/$stream/extras/$basearch/extras-common',
            '    gpgcheck=1', '    EOF',
        ]
        centos=self.root/'images_yaml/centos.yaml'
        centos_repositories = chr(10).join([
            'packages:', '  repositories:', '  - name: BaseOS', '    url: |',
            '      baseurl=https://mirror1.hs-esslingen.de/pub/Mirrors/centos-stream/$stream/BaseOS/$basearch/os/',
            '      gpgcheck=1',
        ])
        centos.write_text(DEFINITION.replace('actions: []', chr(10).join(centos_lines)) + centos_repositories + chr(10))
        image_source_compat.normalize(self.root)
        normalized=self.snapshot()
        image_source_compat.normalize(self.root)
        self.assertEqual(self.snapshot(),normalized)
        self.assertEqual(verify(fedora.read_text())['source']['url'],'https://kojipkgs.fedoraproject.org')
        self.assertIn('/usr/lib/modules/',verify(alma.read_text())['actions'][0]['action'])
        openssh=[s for s in verify(gentoo.read_text())['packages']['sets'] if 'net-misc/openssh' in s['packages']]
        self.assertEqual(len(openssh),1)
        self.assertTrue(any('rc-update add sshd default' in a['action'] for a in verify(gentoo.read_text())['actions']))
        centos_action=verify(centos.read_text())['actions'][0]['action']
        self.assertNotIn('mirror1.hs-esslingen.de',centos_action)
        self.assertEqual(centos_action.count('https://mirror.stream.centos.org/'),3)
        self.assertIn('gpgcheck=1',centos_action)
        repositories=verify(centos.read_text())['packages']['repositories']
        self.assertNotIn('mirror1.hs-esslingen.de',repositories[0]['url'])
        self.assertIn('https://mirror.stream.centos.org/',repositories[0]['url'])
        self.assertIn('gpgcheck=1',repositories[0]['url'])

    def test_centos_stream_source_override_uses_a_slash_terminated_mirror_root(self):
        for repository in ('lxc_amd64_images','lxc_arm_images','lxd_images','incus_images'):
            script=Path(__file__).resolve().parents[2].parent / repository / 'build_images.sh'
            if not script.is_file():
                continue
            source=script.read_text()
            self.assertIn('source.url=https://mirror.stream.centos.org/',source)

    def test_almalinux_bls_normalization_preserves_efi_wrapper_and_is_idempotent(self):
        path = self.root / 'images_yaml/almalinux.yaml'
        source = '''image:
  distribution: almalinux
source:
  downloader: fixture
actions:
- trigger: post-files
  types: [vm]
  releases: [9]
  action: |
    #!/bin/sh
    set -eu
    target=/boot/efi/EFI/almalinux/grub.cfg
    grub2-mkconfig -o "${target}"
    grubby --update-kernel=/boot/vmlinuz-${kver} --args="root=${DISTROBUILDER_ROOT_UUID} ro"
mappings:
  architecture_map: {}
'''
        path.write_text(source)
        hooks.normalize_el_boot(path)
        normalized_action = verify(path.read_text())['actions'][0]['action']
        self.assertIn('target=/boot/grub2/grub.cfg', normalized_action)
        self.assertNotIn('target=/boot/efi/EFI/almalinux/grub.cfg', normalized_action)
        self.assertIn('hosted-compatible-bls', normalized_action)
        self.assertIn('kernel="/boot/vmlinuz-${kver}"', normalized_action)
        normalized = path.read_bytes()
        hooks.normalize_el_boot(path)
        self.assertEqual(path.read_bytes(), normalized)

    def test_failed_partial_source_refresh_preserves_every_original(self):
        before = self.snapshot()

        def failure(root, stage, repo, deadline):
            (stage / "oracle.yaml").write_text("incomplete download")
            raise RuntimeError("fixture transport failure")

        result = refresh.refresh(self.root, "lxc_amd64_images", prepare_stage=failure)
        self.assertEqual(result["status"], "deferred")
        self.assertTrue(result["used_validated_fallback"])
        self.assertEqual(self.snapshot(), before)

    def test_invalid_baseline_cannot_be_reported_as_fallback_success(self):
        (self.root / "images_yaml/openwrt.yaml").write_text("actions: [broken\n")
        with self.assertRaises(Exception):
            refresh.refresh(self.root, "lxc_amd64_images", prepare_stage=lambda *args: [])

    def test_generator_timeout_uses_validated_fallback_without_file_changes(self):
        scripts = self.root / ".github/scripts"
        scripts.mkdir(parents=True)
        for name in ["append_image_actions.py", "verify_image_definitions.py", "ci_network.sh", "image_catalog.py", "image_source_compat.py"]:
            shutil.copy2(SCRIPTS / name, scripts / name)
        (scripts / "refresh_image_definitions.sh").write_text("#!/bin/bash\nsleep 30\n")
        for name in ["bash_insert_content.text", "sh_insert_content.text"]:
            (self.root / name).write_text("[]\n")
        before = self.snapshot()

        def short_budget(root, stage, repo, deadline):
            return refresh.prepare(root, stage, repo, time.monotonic() + 0.1)

        start = time.monotonic()
        with mock.patch.object(refresh, "api_json", return_value={"sha": "a" * 40}):
            result = refresh.refresh(self.root, "lxc_amd64_images", prepare_stage=short_budget)
        self.assertLess(time.monotonic() - start, 5)
        self.assertEqual(result["status"], "deferred")
        self.assertEqual(self.snapshot(), before)

    def test_promotion_failure_rolls_back_previously_installed_files(self):
        before = self.snapshot()
        stage = self.root / "stage"
        stage.mkdir()
        (stage / "all_images.txt").write_text("new-valid-index\n")
        names = ["all_images.txt", "missing.txt"]
        with self.assertRaises(OSError):
            refresh.promote(self.root, stage, names)
        stage.rmdir()
        self.assertEqual(self.snapshot(), before)

    def test_release_indexes_use_uploaded_assets_and_ignore_staging_names(self):
        assets = [
            {"name": "debian_13_trixie_x86_64_cloud.zip", "state": "uploaded", "size": 100},
            {"name": "debian_13_trixie_arm64_cloud.zip", "state": "uploaded", "size": 100},
            {"name": "debian_13_trixie_arm64_default.zip", "state": "new", "size": 100},
            {"name": ".pending-1-debian_13_trixie_arm64_cloud.zip", "state": "uploaded", "size": 100},
            {"name": "oracle_9_9_arm64_cloud.zip", "state": "uploaded", "size": 100},
        ]
        releases = [{"draft": False, "prerelease": False, "tag_name": "debian", "assets": assets, "id": 1}]
        with mock.patch.object(refresh, "api_json", return_value=releases):
            indexes = refresh.release_indexes("incus_images", time.monotonic() + 10)
        self.assertEqual(indexes["x86_64_all_images.txt"], "debian_13_trixie_x86_64_cloud.zip\n")
        self.assertEqual(indexes["arm64_all_images.txt"], "debian_13_trixie_arm64_cloud.zip\n")

    def test_empty_release_catalog_does_not_replace_previous_index(self):
        before = self.snapshot()
        with mock.patch.object(refresh, "api_json", return_value=[]), self.assertRaises(ValueError):
            refresh.release_indexes("lxc_amd64_images", time.monotonic() + 10)
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
