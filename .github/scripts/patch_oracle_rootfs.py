#!/usr/bin/env python3
"""Avoid merging the installed Oracle rootfs over the live ISO filesystem."""
from pathlib import Path
import sys

BEFORE = '''\terr = shared.RsyncLocal(s.ctx, tempRootDir+"/rootfs/", rootfsDir)
\tif err != nil {
\t\treturn fmt.Errorf(`Failed to run "rsync": %w`, err)
\t}

\treturn nil
}'''
AFTER = '''\treturn s.stageOracleRootfs(tempRootDir+"/rootfs/", rootfsDir)
}'''
METHOD = '''
// stageOracleRootfs copies into an empty sibling before replacing the live
// installer tree. Merging the two trees makes rsync inspect inherited ISO
// SELinux labels which can return ENODATA; it also retains installer files.
// Keep -aHASX metadata preservation and propagate every copy/rename error.
func (s *oraclelinux) stageOracleRootfs(source, target string) error {
    staged, err := os.MkdirTemp(filepath.Dir(target), ".oracle-rootfs-")
    if err != nil {
        return fmt.Errorf("Failed to stage Oracle rootfs: %w", err)
    }
    defer os.RemoveAll(staged)
    if err := shared.RsyncLocal(s.ctx, source, staged+"/"); err != nil {
        return fmt.Errorf("Failed to copy Oracle rootfs: %w", err)
    }
    previous := staged + ".previous"
    if err := os.Rename(target, previous); err != nil {
        return fmt.Errorf("Failed to preserve Oracle installer tree: %w", err)
    }
    if err := os.Rename(staged, target); err != nil {
        if restoreErr := os.Rename(previous, target); restoreErr != nil {
            return fmt.Errorf("Failed to install Oracle rootfs: %v; restore: %w", err, restoreErr)
        }
        return fmt.Errorf("Failed to install Oracle rootfs: %w", err)
    }
    if err := os.RemoveAll(previous); err != nil {
        return fmt.Errorf("Failed to clean Oracle installer tree: %w", err)
    }
    return nil
}
'''

def patch(source):
    if 'func (s *oraclelinux) stageOracleRootfs(' in source:
        return source
    if source.count(BEFORE) != 1:
        raise ValueError('Oracle rootfs source contract changed; revalidate the builder')
    return source.replace(BEFORE, AFTER) + METHOD

if __name__ == '__main__':
    path=Path(sys.argv[1])/'sources/oraclelinux-http.go'
    path.write_text(patch(path.read_text()))
    tests=Path(__file__).with_name('fixtures')/'oracle-rootfs-test.go.txt'
    path.with_name('hosted_oracle_rootfs_test.go').write_bytes(tests.read_bytes())
