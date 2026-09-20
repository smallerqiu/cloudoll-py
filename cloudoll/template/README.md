# Cloudoll 4.0.0 example project

This project is a starting point, not a production authorization system. Replace
demo credentials and implement your application's authentication, permissions
and upload policy. Install requirements.txt, configure independent secrets and
read the [deployment documentation](https://cloudoll.chuchur.com/deployment).

# Starting dev server

## with console
```sh
cloudoll start -n myapp 
```

## with vscode
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Myapp",
      "type": "debugpy",
      "request": "launch",
      "console": "integratedTerminal",
      "module": "cloudoll",
      "args": [
        "start",
        "-n",
        "myapp",
        "-env",
        "local",
        "-m",
        "development"
      ],
      "cwd": "${workspaceFolder}"
    }
  ]
}
```

# Production environment deployment
Cloudoll production mode runs in the foreground. Use a process manager for
automatic restarts and its own stop/restart commands. Create config/conf.prod.yaml
before selecting -env prod; a missing configuration file is an error.

## with systemd
create service file `/etc/systemd/system/myapp.service` (only for linux)
```ini
[Unit]
Description=My Service
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/cloudoll start -n myapp -m production -env prod
WorkingDirectory=/opt/myapp
Restart=always
RestartSec=5
TimeoutStopSec=90
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal
LimitNOFILE=65535
; User=cloudolluser
; Group=cloudollgroup

[Install]
WantedBy=multi-user.target
```
then you can use systemctl to start your service
```bash
# start
systemctl start myapp.service
# status
systemctl status myapp.service
# stop
systemctl stop myapp.service
# restart
systemctl restart myapp.service
# enable
systemctl enable myapp.service
```

## with docker

```dockerfile

FROM python:3.13-slim

WORKDIR /app
EXPOSE 9001
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY . .

CMD ["/usr/local/bin/cloudoll", "start", "-n", "myapp", "-m", "production", "-env", "prod", "--host", "0.0.0.0"]
```

## with suporvisor
create config file `/etc/supervisord.conf`
```ini
[unix_http_server]
file=/app/bin/supervisor.sock

[supervisorctl]
serverurl=unix:///app/bin/supervisor.sock

[supervisord]
nodaemon=true 
logfile_backups=1
loglevel=info
logfile_maxbytes=100MB
pidfile=/app/bin/supervisord.pid
logfile=/app/logs/supervisord.log
# user=root

[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

[program:myapp]
command=/usr/local/bin/cloudoll start -n myapp -m production -env prod
process_name=myapp
numprocs=1
directory=/app
autostart=true
autorestart=true
stopsignal=TERM
stopwaitsecs=90
stopasgroup=true
killasgroup=true
redirect_stderr=true
stdout_logfile=/app/logs/myapp.log
```

Keep one process-management authority per service. Coordinate its stop timeout
with request draining, resource cleanup and any application-owned background work.
