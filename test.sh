#!/bin/bash
# by https://github.com/oneclickvirt/lxc_amd64_images
# 2024.03.25
# curl -L https://raw.githubusercontent.com/oneclickvirt/lxc_amd64_images/main/test.sh -o test.sh && chmod +x test.sh && ./test.sh

rm -rf log
rm -rf fixed_images.txt
date=$(date)
system_names=()
echo "$date" >>log
echo "------------------------------------------" >>log
release_names=("ubuntu" "debian" "kali" "centos" "almalinux" "rockylinux" "fedora" "opensuse" "alpine" "archlinux" "gentoo" "openwrt" "oracle" "openeuler")
response=$(curl -slk -m 6 "https://raw.githubusercontent.com/oneclickvirt/lxc_amd64_images/main/all_images.txt")
if [ $? -ne 0 ]; then
    response=$(curl -slk -m 6 "https://cdn.spiritlhl.net/https://raw.githubusercontent.com/oneclickvirt/lxc_amd64_images/main/all_images.txt")
fi
if [ $? -eq 0 ] && [ -n "$response" ]; then
    system_names+=($(echo "$response"))
fi
for ((i = 0; i < ${#release_names[@]}; i++)); do
    release_name="${release_names[i]}"
    temp_images=()
    for sy in "${system_names[@]}"; do
        if [[ $sy == "${release_name}"* ]]; then
            curl -m 60 -LO "https://github.com/oneclickvirt/lxc_amd64_images/releases/download/${release_name}/${sy}"
            if [ $? -ne 0 ]; then
                curl -m 60 -LO "https://cdn.spiritlhl.net/https://github.com/oneclickvirt/lxc_amd64_images/releases/download/${release_name}/${sy}"
            fi
            temp_images+=("${sy}")
        fi
    done
    for image in "${temp_images[@]}"; do
        echo "$image"
        echo "$image" >>log
        echo "$image" >>fixed_images.txt
        delete_status=false
        pct create 102 "$image" -cores 2 -cpuunits 1024 -memory 2048 -swap 0 -rootfs local:10 -onboot 1 -features nesting=1
        pct start 102
        pct set 102 --hostname 102
        res0=$(pct set 102 --net0 name=eth0,ip=172.16.1.111/24,bridge=vmbr1,gw=172.16.1.1)
        if [[ $res0 == *"error"* || $res0 == *"failed: exit code"* ]]; then
            echo "set eth0 failed" >>log
            if [ "$delete_status" = false ];then
                delete_status=true
                head -n -1 fixed_images.txt > temp.txt && mv temp.txt fixed_images.txt
            fi
        fi
        pct set 102 --nameserver 1.1.1.1
        pct set 102 --searchdomain local
        sleep 6
        res1=$(pct exec 102 -- lsof -i:22)
        if [[ $res1 == *"command not found"* ]]; then
            echo "no lsof" >>log
        fi
        sleep 1
        res1=$(pct exec 102 -- lsof -i:22)
        if [[ $res1 == *"ssh"* ]]; then
            echo "ssh config correct"
        else
            if [ "$delete_status" = false ];then
                delete_status=true
                head -n -1 fixed_images.txt > temp.txt && mv temp.txt fixed_images.txt
            fi
        fi
        res2=$(pct exec 102 -- curl --version)
        if [[ $res2 == *"command not found"* ]]; then
            echo "no curl" >>log
        fi
        res3=$(pct exec 102 -- wget --version)
        if [[ $res3 == *"command not found"* ]]; then
            echo "no wget" >>log
        fi
        echo "nameserver 8.8.8.8" | pct exec 102 -- tee -a /etc/resolv.conf
        res4=$(pct exec 102 -- curl -lk https://cdn.spiritlhl.net/https://raw.githubusercontent.com/spiritLHLS/ecs/main/back/test)
        if [[ $res4 == *"success"* ]]; then
            echo "network is public"
        else
            echo "no public network" >>log
            if [ "$delete_status" = false ];then
                delete_status=true
                head -n -1 fixed_images.txt > temp.txt && mv temp.txt fixed_images.txt
            fi
        fi
        pct stop 102
        if [ $? -eq 0 ]; then
            pct start 102
            sleep 10
            echo "nameserver 8.8.8.8" | pct exec 102 -- tee -a /etc/resolv.conf
            res5=$(pct exec 102 -- curl -lk https://cdn.spiritlhl.net/https://raw.githubusercontent.com/spiritLHLS/ecs/main/back/test)
            if [[ $res5 == *"success"* ]]; then
                echo "reboot success"
            else
                echo "reboot failed" >>log
                if [ "$delete_status" = false ];then
                    delete_status=true
                    head -n -1 fixed_images.txt > temp.txt && mv temp.txt fixed_images.txt
                fi
            fi
        else
            echo "reboot failed" >>log
            if [ "$delete_status" = false ];then
                delete_status=true
                head -n -1 fixed_images.txt > temp.txt && mv temp.txt fixed_images.txt
            fi
        fi
        pct stop 102
        pct destroy 102
        rm -rf $image
        echo "------------------------------------------" >>log
    done
done
