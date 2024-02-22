#!/bin/bash
# by https://github.com/oneclickvirt/lxc_amd64_images
# 2024.02.22
# curl -L https://raw.githubusercontent.com/oneclickvirt/lxc_amd64_images/main/test.sh -o test.sh && chmod +x test.sh && ./test.sh

rm -rf log
release_names=("ubuntu" "debian" "kali" "centos" "almalinux" "rockylinux" "fedora" "opensuse" "alpine" "openeuler" "archlinux")
response=$(curl -slk -m 6 "https://raw.githubusercontent.com/oneclickvirt/lxc_amd64_images/main/fixed_images.txt")
system_names=()
if [ $? -eq 0 ] && [ -n "$response" ]; then
    system_names+=($(echo "$response"))
fi
for ((i=0; i<${#release_names[@]}; i++)); do
    release_name="${release_names[i]}"
    temp_images=()
    for sy in "${system_names[@]}"; do
        if [[ $sy == "${release_name}"* ]]; then
            curl -LO "https://github.com/oneclickvirt/lxc_amd64_images/releases/download/${release_name}/${sy}"
            temp_images+=("${sy}")
        fi
    done
    for image in "${temp_images[@]}"; do
      echo "$image"
      echo "$image" >> log
      pct create 102 "$image" -cores 6 -cpuunits 1024 -memory 26480 -swap 0 -rootfs local:10 -onboot 1 -features nesting=1
      pct start 102
      pct set 102 --hostname 102
      res0=$(pct set 102 --net0 name=eth0,ip=172.16.1.111/24,bridge=vmbr1,gw=172.16.1.1)
      if [[ $res0 == *"error"* || $res0 == *"failed: exit code"* ]]; then
          echo "set eth0 failed" >> log
      fi
      pct set 102 --nameserver 1.1.1.1
      pct set 102 --searchdomain local
      sleep 6
      res1=$(pct exec 102 -- lsof -i:22)
      if [[ $res1 == *"command not found"* ]]; then
          echo "no lsof" >> log
      fi
      sleep 1
      res1=$(pct exec 102 -- lsof -i:22)
      if [[ $res1 == *"ssh"* ]]; then
          echo "ssh config correct"
      fi
      res2=$(pct exec 102 -- curl --version)
      if [[ $res2 == *"command not found"* ]]; then
          echo "no curl" >> log
      fi
      res3=$(pct exec 102 -- wget --version)
      if [[ $res3 == *"command not found"* ]]; then
          echo "no wget" >> log
      fi
      echo "nameserver 8.8.8.8" | pct exec 102 -- tee -a /etc/resolv.conf
      res4=$(pct exec 102 -- curl -lk https://raw.githubusercontent.com/spiritLHLS/ecs/main/back/test)
      if [[ $res4 == *"success"* ]]; then
          echo "network is public"
      else
          echo "no public network" >> log
      fi
      pct stop 102
      pct start 102
      sleep 10
      echo "nameserver 8.8.8.8" | pct exec 102 -- tee -a /etc/resolv.conf
      res5=$(pct exec 102 -- curl -lk https://raw.githubusercontent.com/spiritLHLS/ecs/main/back/test)
      if [[ $res5 == *"success"* ]]; then
          echo "reboot success"
      else
          echo "reboot failed" >> log
      fi
      pct stop 102
      pct destroy 102
      echo "------------------------------------------" >> log
    done
done
