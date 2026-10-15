# Hosted image maintenance

## Builds and runtime checks

Image production uses disposable GitHub-hosted Ubuntu AMD64/ARM64 runners. Containers use Incus or LXD. VM tests use KVM when it can create a VM; otherwise they use bounded QEMU software emulation. No scheduled image workflow requires a private runner.

The validated upstream catalog drives both listing and building. `CI_IMAGE_RELEASES` and the manual release/architecture/variant inputs select exact outputs. Listing is read-only. Scheduled builds select the supported current catalog; development releases such as edge, snapshot and forky remain manual.

Every accepted image must pass archive/OS identity checks, guest execution, an SSH listener, certificate-verified HTTPS/DNS and a changed boot ID after restart. A job with no accepted output cannot claim image validation. Software-emulation success does not certify a separate production Proxmox host.

## Failed sources and publication

`.github/image-build-quarantine.json` identifies observed failing distribution/release/architecture/type combinations and links their evidence. Scheduled builds and automatic builds triggered by upstream refresh omit those combinations and retain previous assets. An empty automatic matrix explicitly skips its build job. Manual dispatch can retry quarantined combinations without bypassing any acceptance gate. Remove a hold only after all affected variants pass real validation and publication; a cloud-only pass does not certify default or systemd variants.

Classified transient downloads can retry once within a shared build budget. Signature, checksum and certificate failures remain errors. The publisher stages and validates a complete batch before replacing release assets and restores earlier assets if replacement fails. Failed builders and leftover intermediate files cannot satisfy publication checks.

## Upstream refreshes

A refresh stages all 14 definitions, reapplies compatibility fixes, validates the full catalog and release indexes, then promotes the snapshot transactionally. Download, timeout, malformed YAML, duplicate keys, empty indexes and concurrent maintenance failures retain the validated previous snapshot. The quarantine policy and maintained scripts are outside generated paths.

Compatibility normalization preserves Fedora bootstrap ordering; Debian first-boot SSH host keys; Gentoo cloud boot dependencies; SUSE SSH packages, cloud-init local stage and resolver ownership; vendor ARM EFI package names; and EL kernel, BLS and EFI paths. Native SUSE archives retain vendor-managed DNS symlinks. Raw LXC cloud images remove the disable flag written by the LXC cloud-init generator and restore their cloud-init services. Consumers still provide their own NoCloud/network/DNS data.

Definitions and catalog axes come from one resolved LXC CI commit. The builder compiles the official SHA256-pinned distrobuilder 3.4.0 release with vendored dependencies and checked Oracle ISO/CentOS mirror compatibility repairs. Failed integrity or compilation checks stop publication. The old stable Snap is not a compatible fallback for current OpenWrt and Gentoo definitions.
