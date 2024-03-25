## runner

```
export RUNNER_ALLOW_RUNASROOT=1
```

```
./config.sh xxxxxxxxxxxxxxxxxxxxxxx
```

```
nano /etc/systemd/system/github-runner.service
```

```
[Unit]
Description=GitHub Actions Runner

[Service]
Type=simple
WorkingDirectory=/root/actions-runner
ExecStart=/root/actions-runner/run.sh
User=root
Restart=always
Environment="RUNNER_ALLOW_RUNASROOT=1"

[Install]
WantedBy=multi-user.target
```

```
sudo systemctl daemon-reload
sudo systemctl start github-runner
```

```
sudo systemctl status github-runner
```

```
sudo systemctl enable github-runner
```
