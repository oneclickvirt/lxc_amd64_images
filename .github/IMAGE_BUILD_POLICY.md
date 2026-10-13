# Image build recovery

Build/list commands use the same exact release selector (`CI_IMAGE_RELEASES`). Listing is read-only. Unknown or empty catalogs fail before publication; a failed builder never publishes partial output. Image archives are validated according to their actual ZIP or tar.xz format. The publisher stages and checks the entire batch before replacing existing release assets and restores previous assets if replacement fails.

Legacy full-catalog Incus/LXD container and VM generation and the ARM LXC catalog are manual while their upstream bootstrap sources need per-release verification. Select distro, release and architecture in workflow_dispatch. Scheduled index refresh remains enabled and uses already complete metadata/rootfs pairs. Existing downloadable images are retained. Rocky 10 automatic builds are paused because the configured upstream signing key does not validate its packages; GPG verification must remain enabled. AMD64 Rocky scheduled builds select 8/9; Ubuntu selects jammy/noble/resolute. Other manual historical releases are not certified by this change.

AMD64 CentOS schedules only 9-Stream; retired 7/8-Stream are manual. Debian schedules bookworm/trixie; development forky and retired bullseye are manual. The checked-in Debian/Ubuntu release catalogs remain a bounded fallback when upstream catalog retrieval fails. Empty unknown catalogs still fail and retain prior assets.

Image definitions are parsed with duplicate-key rejection before runner provisioning and in Action policy. OpenWrt 25.12/snapshot use apk and older lines use opkg; OpenWrt schedules select stable 25.12, with snapshot manual. Oracle 9/10 use the official ISO endpoint rather than the stale mirror; Oracle 10 is manual until separately verified. ARM Alma/Rocky definitions retain vendor GPG keys and no longer fall back to disabling package/ISO verification.

OpenWrt and Oracle 10 require distrobuilder 3.4.0. These workflow paths compile the official SHA256-pinned, vendored release using the upstream build tags; the older stable Snap is not a compatible fallback. Failed download/checksum/compilation stops before image publication.

Oracle 8/9/10 use the official ISO host on these distrobuilder paths. The pinned 3.4.0 source receives one checked compatibility patch for the official OL8 versioned ISO filename; GPG package verification remains enabled. This avoids relying on the intermittently unreachable third-party OL8 mirror.

OpenWrt rootfs archives can validly be smaller than 10 MiB. They use a 1 MiB compressed size floor plus full XZ/tar integrity and an etc/openwrt_release identity check; other images retain the 10 MiB floor. ZIP CRC checks and maximum size limits remain enabled.
