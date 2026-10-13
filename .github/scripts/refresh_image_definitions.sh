#!/bin/bash
set -eo pipefail
source "$CI_IMAGE_SCRIPT_ROOT/ci_network.sh"
# from https://github.com/oneclickvirt/lxc_amd64_images
# Thanks https://github.com/lxc/lxc-ci/tree/main/images

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${REPO_ROOT}/images_yaml/"

# debian
rm -rf debian.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/debian.yaml
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cron"
sed -i "/- vim/ a\\$insert_content_1" debian.yaml
"$CI_IMAGE_PYTHON" "$CI_IMAGE_SCRIPT_ROOT/append_image_actions.py" "debian.yaml" "$CI_IMAGE_SCRIPT_ROOT/../../bash_insert_content.text"
sed -i -e '/mappings:/i \ ' debian.yaml

# ubuntu
rm -rf ubuntu.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/ubuntu.yaml
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cron"
sed -i "/- vim/ a\\$insert_content_1" ubuntu.yaml
"$CI_IMAGE_PYTHON" "$CI_IMAGE_SCRIPT_ROOT/append_image_actions.py" "ubuntu.yaml" "$CI_IMAGE_SCRIPT_ROOT/../../bash_insert_content.text"
sed -i -e '/mappings:/i \ ' ubuntu.yaml

# kali
rm -rf kali.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/kali.yaml
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cron"
sed -i "/- systemd/ a\\$insert_content_1" kali.yaml
"$CI_IMAGE_PYTHON" "$CI_IMAGE_SCRIPT_ROOT/append_image_actions.py" "kali.yaml" "$CI_IMAGE_SCRIPT_ROOT/../../bash_insert_content.text"
sed -i -e '/mappings:/i \ ' kali.yaml

# centos
rm -rf centos.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/centos.yaml
# epel-relase 不可用 cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
sed -i "/- vim-minimal/ a\\$insert_content_1" centos.yaml
"$CI_IMAGE_PYTHON" "$CI_IMAGE_SCRIPT_ROOT/append_image_actions.py" "centos.yaml" "$CI_IMAGE_SCRIPT_ROOT/../../bash_insert_content.text"

# almalinux
rm -rf almalinux.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/almalinux.yaml
# cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
sed -i "/- vim-minimal/ a\\$insert_content_1" almalinux.yaml
"$CI_IMAGE_PYTHON" "$CI_IMAGE_SCRIPT_ROOT/append_image_actions.py" "almalinux.yaml" "$CI_IMAGE_SCRIPT_ROOT/../../bash_insert_content.text"

# rockylinux
rm -rf rockylinux.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/rockylinux.yaml
# cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
sed -i "/- vim-minimal/ a\\$insert_content_1" rockylinux.yaml
"$CI_IMAGE_PYTHON" "$CI_IMAGE_SCRIPT_ROOT/append_image_actions.py" "rockylinux.yaml" "$CI_IMAGE_SCRIPT_ROOT/../../bash_insert_content.text"

# oracle
rm -rf oracle.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/oracle.yaml
# cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
sed -i "/- vim-minimal/ a\\$insert_content_1" oracle.yaml
"$CI_IMAGE_PYTHON" "$CI_IMAGE_SCRIPT_ROOT/append_image_actions.py" "oracle.yaml" "$CI_IMAGE_SCRIPT_ROOT/../../bash_insert_content.text"

# archlinux
rm -rf archlinux.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/archlinux.yaml
# cronie 不可用 cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - iptables\n    - dos2unix"
sed -i "/- which/ a\\$insert_content_1" archlinux.yaml
"$CI_IMAGE_PYTHON" "$CI_IMAGE_SCRIPT_ROOT/append_image_actions.py" "archlinux.yaml" "$CI_IMAGE_SCRIPT_ROOT/../../bash_insert_content.text"
sed -i -e '/mappings:/i \ ' archlinux.yaml

# gentoo
rm -rf gentoo.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/gentoo.yaml
# cronie 不可用 cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - iptables\n    - dos2unix"
sed -i "/- sudo/ a\\$insert_content_1" gentoo.yaml
"$CI_IMAGE_PYTHON" "$CI_IMAGE_SCRIPT_ROOT/append_image_actions.py" "gentoo.yaml" "$CI_IMAGE_SCRIPT_ROOT/../../bash_insert_content.text"
sed -i -e '/environment:/i \ ' gentoo.yaml
sed -i 's/- default/- openrc/g' gentoo.yaml

# fedora
rm -rf fedora.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/fedora.yaml
# cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
sed -i "/- xz/ a\\$insert_content_1" fedora.yaml
"$CI_IMAGE_PYTHON" "$CI_IMAGE_SCRIPT_ROOT/append_image_actions.py" "fedora.yaml" "$CI_IMAGE_SCRIPT_ROOT/../../bash_insert_content.text"

# alpine
rm -rf alpine.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/alpine.yaml
# cronie 不可用 cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - openssh-keygen\n    - cronie\n    - iptables\n    - dos2unix"
sed -i "/- doas/ a\\$insert_content_1" alpine.yaml
"$CI_IMAGE_PYTHON" "$CI_IMAGE_SCRIPT_ROOT/append_image_actions.py" "alpine.yaml" "$CI_IMAGE_SCRIPT_ROOT/../../sh_insert_content.text"
sed -i -e '/mappings:/i \ ' alpine.yaml

# openwrt
rm -rf openwrt.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/openwrt.yaml
# cronie 不可用 cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - openssh-keygen\n    - iptables"
sed -i "/- sudo/ a\\$insert_content_1" openwrt.yaml
"$CI_IMAGE_PYTHON" "$CI_IMAGE_SCRIPT_ROOT/append_image_actions.py" "openwrt.yaml" "$CI_IMAGE_SCRIPT_ROOT/../../sh_insert_content.text"

# opensuse
rm -rf opensuse.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/opensuse.yaml
# cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
sed -i "/- vim-minimal/ a\\$insert_content_1" opensuse.yaml
"$CI_IMAGE_PYTHON" "$CI_IMAGE_SCRIPT_ROOT/append_image_actions.py" "opensuse.yaml" "$CI_IMAGE_SCRIPT_ROOT/../../bash_insert_content.text"

# openeuler
rm -rf openeuler.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/openeuler.yaml
# cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
sed -i "/- vim-minimal/ a\\$insert_content_1" openeuler.yaml
"$CI_IMAGE_PYTHON" "$CI_IMAGE_SCRIPT_ROOT/append_image_actions.py" "openeuler.yaml" "$CI_IMAGE_SCRIPT_ROOT/../../bash_insert_content.text"

cd "${REPO_ROOT}"
