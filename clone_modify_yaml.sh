#!/bin/bash
# from https://github.com/oneclickvirt/lxc_amd64_images
# Thanks https://github.com/lxc/lxc-ci/tree/main/images

cd /home/runner/work/lxc_amd64_images/lxc_amd64_images/images_yaml/

# debian
rm -rf debian.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/debian.yaml
chmod 777 debian.yaml
sed -i '/^files:/a\  - path: /dev\n    exclude: true\n  - path: /proc\n    exclude: true\n  - path: /sys\n    exclude: true\n  - path: /run\n    exclude: true' debian.yaml
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cron"
sed -i "/- vim/ a\\$insert_content_1" debian.yaml
insert_content_2=$(cat /home/runner/work/lxc_amd64_images/lxc_amd64_images/bash_insert_content.text)
line_number=$(($(wc -l < debian.yaml) - 2))
head -n $line_number debian.yaml > temp.yaml
echo "$insert_content_2" >> temp.yaml
tail -n 2 debian.yaml >> temp.yaml
mv temp.yaml debian.yaml
sed -i -e '/mappings:/i \ ' debian.yaml

# ubuntu
rm -rf ubuntu.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/ubuntu.yaml
chmod 777 ubuntu.yaml
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cron"
sed -i "/- vim/ a\\$insert_content_1" ubuntu.yaml
insert_content_2=$(cat /home/runner/work/lxc_amd64_images/lxc_amd64_images/bash_insert_content.text)
line_number=$(($(wc -l < ubuntu.yaml) - 2))
head -n $line_number ubuntu.yaml > temp.yaml
echo "$insert_content_2" >> temp.yaml
tail -n 2 ubuntu.yaml >> temp.yaml
mv temp.yaml ubuntu.yaml
sed -i -e '/mappings:/i \ ' ubuntu.yaml

# kali
rm -rf kali.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/kali.yaml
chmod 777 kali.yaml
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cron"
sed -i "/- systemd/ a\\$insert_content_1" kali.yaml
insert_content_2=$(cat /home/runner/work/lxc_amd64_images/lxc_amd64_images/bash_insert_content.text)
line_number=$(($(wc -l < kali.yaml) - 2))
head -n $line_number kali.yaml > temp.yaml
echo "$insert_content_2" >> temp.yaml
tail -n 2 kali.yaml >> temp.yaml
mv temp.yaml kali.yaml
sed -i -e '/mappings:/i \ ' kali.yaml

# centos
rm -rf centos.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/centos.yaml
chmod 777 centos.yaml
# epel-relase 不可用 cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
sed -i "/- vim-minimal/ a\\$insert_content_1" centos.yaml
insert_content_2=$(cat /home/runner/work/lxc_amd64_images/lxc_amd64_images/bash_insert_content.text)
cat centos.yaml > temp.yaml
echo "" >> temp.yaml
echo "$insert_content_2" >> temp.yaml
mv temp.yaml centos.yaml

# almalinux
rm -rf almalinux.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/almalinux.yaml
chmod 777 almalinux.yaml
# cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
sed -i "/- vim-minimal/ a\\$insert_content_1" almalinux.yaml
insert_content_2=$(cat /home/runner/work/lxc_amd64_images/lxc_amd64_images/bash_insert_content.text)
cat almalinux.yaml > temp.yaml
echo "" >> temp.yaml
echo "$insert_content_2" >> temp.yaml
mv temp.yaml almalinux.yaml

# rockylinux
rm -rf rockylinux.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/rockylinux.yaml
chmod 777 rockylinux.yaml
# cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
sed -i "/- vim-minimal/ a\\$insert_content_1" rockylinux.yaml
insert_content_2=$(cat /home/runner/work/lxc_amd64_images/lxc_amd64_images/bash_insert_content.text)
cat rockylinux.yaml > temp.yaml
echo "" >> temp.yaml
echo "$insert_content_2" >> temp.yaml
mv temp.yaml rockylinux.yaml

# oracle
rm -rf oracle.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/oracle.yaml
chmod 777 oracle.yaml
# cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
sed -i "/- vim-minimal/ a\\$insert_content_1" oracle.yaml
insert_content_2=$(cat /home/runner/work/lxc_amd64_images/lxc_amd64_images/bash_insert_content.text)
cat oracle.yaml > temp.yaml
echo "" >> temp.yaml
echo "$insert_content_2" >> temp.yaml
mv temp.yaml oracle.yaml

# archlinux
rm -rf archlinux.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/archlinux.yaml
chmod 777 archlinux.yaml
# cronie 不可用 cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - iptables\n    - dos2unix"
sed -i "/- which/ a\\$insert_content_1" archlinux.yaml
insert_content_2=$(cat /home/runner/work/lxc_amd64_images/lxc_amd64_images/bash_insert_content.text)
line_number=$(($(wc -l < archlinux.yaml) - 2))
head -n $line_number archlinux.yaml > temp.yaml
echo "$insert_content_2" >> temp.yaml
tail -n 2 archlinux.yaml >> temp.yaml
mv temp.yaml archlinux.yaml
sed -i -e '/mappings:/i \ ' archlinux.yaml

# gentoo
rm -rf gentoo.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/gentoo.yaml
chmod 777 gentoo.yaml
# cronie 不可用 cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - iptables\n    - dos2unix"
sed -i "/- sudo/ a\\$insert_content_1" gentoo.yaml
insert_content_2=$(cat /home/runner/work/lxc_amd64_images/lxc_amd64_images/bash_insert_content.text)
line_number=$(($(wc -l < gentoo.yaml) - 3))
head -n $line_number gentoo.yaml > temp.yaml
echo "$insert_content_2" >> temp.yaml
tail -n 3 gentoo.yaml >> temp.yaml
mv temp.yaml gentoo.yaml
sed -i -e '/environment:/i \ ' gentoo.yaml
sed -i 's/- default/- openrc/g' gentoo.yaml

# fedora
rm -rf fedora.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/fedora.yaml
chmod 777 fedora.yaml
# cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
sed -i "/- xz/ a\\$insert_content_1" fedora.yaml
insert_content_2=$(cat /home/runner/work/lxc_amd64_images/lxc_amd64_images/bash_insert_content.text)
cat fedora.yaml > temp.yaml
echo "" >> temp.yaml
echo "$insert_content_2" >> temp.yaml
mv temp.yaml fedora.yaml

# alpine
rm -rf alpine.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/alpine.yaml
chmod 777 alpine.yaml
# cronie 不可用 cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - openssh-keygen\n    - cronie\n    - iptables\n    - dos2unix"
sed -i "/- doas/ a\\$insert_content_1" alpine.yaml
insert_content_2=$(cat /home/runner/work/lxc_amd64_images/lxc_amd64_images/sh_insert_content.text)
line_number=$(($(wc -l < alpine.yaml) - 2))
head -n $line_number alpine.yaml > temp.yaml
echo "$insert_content_2" >> temp.yaml
tail -n 2 alpine.yaml >> temp.yaml
mv temp.yaml alpine.yaml
sed -i -e '/mappings:/i \ ' alpine.yaml

# openwrt
rm -rf openwrt.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/openwrt.yaml
chmod 777 openwrt.yaml
# cronie 不可用 cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - openssh-keygen\n    - iptables"
sed -i "/- sudo/ a\\$insert_content_1" openwrt.yaml
insert_content_2=$(cat /home/runner/work/lxc_amd64_images/lxc_amd64_images/sh_insert_content.text)
cat openwrt.yaml > temp.yaml
echo "$insert_content_2" >> temp.yaml
mv temp.yaml openwrt.yaml

# opensuse
rm -rf opensuse.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/opensuse.yaml
chmod 777 opensuse.yaml
# cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
sed -i "/- vim-minimal/ a\\$insert_content_1" opensuse.yaml
insert_content_2=$(cat /home/runner/work/lxc_amd64_images/lxc_amd64_images/bash_insert_content.text)
cat opensuse.yaml > temp.yaml
echo "" >> temp.yaml
echo "$insert_content_2" >> temp.yaml
mv temp.yaml opensuse.yaml

# openeuler
rm -rf openeuler.yaml
wget https://raw.githubusercontent.com/lxc/lxc-ci/main/images/openeuler.yaml
chmod 777 openeuler.yaml
# cron 不可用
insert_content_1="    - curl\n    - wget\n    - bash\n    - lsof\n    - sshpass\n    - openssh-server\n    - iptables\n    - dos2unix\n    - cronie"
sed -i "/- vim-minimal/ a\\$insert_content_1" openeuler.yaml
insert_content_2=$(cat /home/runner/work/lxc_amd64_images/lxc_amd64_images/bash_insert_content.text)
cat openeuler.yaml > temp.yaml
echo "" >> temp.yaml
echo "$insert_content_2" >> temp.yaml
mv temp.yaml openeuler.yaml

cd /home/runner/work/lxc_amd64_images/lxc_amd64_images
# 更新支持的镜像列表
build_or_list_images() {
    local versions=()
    local ver_nums=()
    local variants=()
    read -ra versions <<< "$1"
    read -ra ver_nums <<< "$2"
    read -ra variants <<< "$3"
    local architectures=("$build_arch")
    local len=${#versions[@]}
    for ((i = 0; i < len; i++)); do
        version=${versions[i]}
        ver_num=${ver_nums[i]}
        for arch in "${architectures[@]}"; do
            for variant in "${variants[@]}"; do
                local url="https://github.com/oneclickvirt/lxc_amd64_images/releases/download/${run_funct}/${run_funct}_${ver_num}_${version}_${arch}_${variant}.tar.xz"
                if curl --output /dev/null --silent --head --fail "$url"; then
                    echo "${run_funct}_${ver_num}_${version}_${arch}_${variant}.tar.xz" >> all_images.txt
                else
                    echo "File not found: $url"
                fi
            done
        done
    done
}

# 不同发行版的配置
# build_or_list_images 镜像名字 镜像版本号 variants的值
build_arch="x86_64"
run_funct="debian"
build_or_list_images "buster bullseye bookworm trixie" "10 11 12 13" "default cloud"
run_funct="ubuntu"
build_or_list_images "bionic focal jammy lunar mantic noble" "18.04 20.04 22.04 23.04 23.10 24.04" "default cloud"
run_funct="kali"
build_or_list_images "kali-rolling" "latest" "default cloud"
run_funct="archlinux"
build_or_list_images "current" "current" "default cloud"
run_funct="gentoo"
build_or_list_images "current" "current" "cloud systemd openrc"
run_funct="centos"
build_or_list_images "7 8-Stream 9-Stream" "7 8 9" "default cloud"
run_funct="almalinux"
URL="https://raw.githubusercontent.com/lxc/lxc-ci/main/jenkins/jobs/image-almalinux.yaml"
curl_output=$(curl -s "$URL" | awk '/name: release/{flag=1; next} /^$/{flag=0} flag && /^ *-/{if (!first) {printf "%s", $2; first=1} else {printf " %s", $2}}' | sed 's/"//g')
build_or_list_images "$curl_output" "$curl_output" "default cloud"
run_funct="rockylinux"
URL="https://raw.githubusercontent.com/lxc/lxc-ci/main/jenkins/jobs/image-rockylinux.yaml"
curl_output=$(curl -s "$URL" | awk '/name: release/{flag=1; next} /^$/{flag=0} flag && /^ *-/{if (!first) {printf "%s", $2; first=1} else {printf " %s", $2}}' | sed 's/"//g')
build_or_list_images "$curl_output" "$curl_output" "default cloud"
run_funct="alpine"
URL="https://raw.githubusercontent.com/lxc/lxc-ci/main/jenkins/jobs/image-alpine.yaml"
curl_output=$(curl -s "$URL" | awk '/name: release/{flag=1; next} /^$/{flag=0} flag && /^ *-/{if (!first) {printf "%s", $2; first=1} else {printf " %s", $2}}' | sed 's/"//g')
build_or_list_images "$curl_output" "$curl_output" "default cloud"
run_funct="openwrt"
URL="https://raw.githubusercontent.com/lxc/lxc-ci/main/jenkins/jobs/image-openwrt.yaml"
curl_output=$(curl -s "$URL" | awk '/name: release/{flag=1; next} /^$/{flag=0} flag && /^ *-/{if (!first) {printf "%s", $2; first=1} else {printf " %s", $2}}' | sed 's/"//g')
build_or_list_images "$curl_output" "$curl_output" "default cloud"
run_funct="oracle"
URL="https://raw.githubusercontent.com/lxc/lxc-ci/main/jenkins/jobs/image-oracle.yaml"
curl_output=$(curl -s "$URL" | awk '/name: release/{flag=1; next} /^$/{flag=0} flag && /^ *-/{if (!first) {printf "%s", $2; first=1} else {printf " %s", $2}}' | sed 's/"//g')
build_or_list_images "$curl_output" "$curl_output" "default cloud"
run_funct="fedora"
URL="https://raw.githubusercontent.com/lxc/lxc-ci/main/jenkins/jobs/image-fedora.yaml"
curl_output=$(curl -s "$URL" | awk '/name: release/{flag=1; next} /^$/{flag=0} flag && /^ *-/{if (!first) {printf "%s", $2; first=1} else {printf " %s", $2}}' | sed 's/"//g')
build_or_list_images "$curl_output" "$curl_output" "default cloud"
run_funct="opensuse"
URL="https://raw.githubusercontent.com/lxc/lxc-ci/main/jenkins/jobs/image-opensuse.yaml"
curl_output=$(curl -s "$URL" | awk '/name: release/{flag=1; next} /^$/{flag=0} flag && /^ *-/{if (!first) {printf "%s", $2; first=1} else {printf " %s", $2}}' | sed 's/"//g')
build_or_list_images "$curl_output" "$curl_output" "default cloud"
run_funct="openeuler"
URL="https://raw.githubusercontent.com/lxc/lxc-ci/main/jenkins/jobs/image-openeuler.yaml"
curl_output=$(curl -s "$URL" | awk '/name: release/{flag=1; next} /^$/{flag=0} flag && /^ *-/{if (!first) {printf "%s", $2; first=1} else {printf " %s", $2}}' | sed 's/"//g')
build_or_list_images "$curl_output" "$curl_output" "default cloud"
# 去除重复行
remove_duplicate_lines() {
    # 预处理：去除行尾空格和制表符
    sed -i 's/[ \t]*$//' "$1"
    # 去除重复行并跳过空行和注释行
    if [ -f "$1" ]; then
        awk '{ line = $0; gsub(/^[ \t]+/, "", line); gsub(/[ \t]+/, " ", line); if (!NF || !seen[line]++) print $0 }' "$1" >"$1.tmp" && mv -f "$1.tmp" "$1"
    fi
}
remove_duplicate_lines "all_images.txt"
sed -i '/^$/d' "all_images.txt"
