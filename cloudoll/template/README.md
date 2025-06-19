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
    },
  ]
}
```

# Production environment deployment
In production environment, dont' suggest to use cloudoll to start your application.
You can use a daemon to deploy your application. like supervisor or pm2 or systemd.

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
systemctl start myservice.service 
# status
systemctl status myservice.service
# stop
systemctl stop myservice.service
# restart
systemctl restart myservice.service
# enable
systemctl enable myservice.service
```

## with docker

```dockerfile

FROM python:3

WORKDIR /app
EXPOSE 9001
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY . .

CMD ["/usr/local/bin/cloudoll","start" ,"-n", "myapp", "-m", "production", "-env", "prod"]
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
redirect_stderr=true
stdout_logfile=/app/logs/myapp.log
```

## with pm2
create ecosystem.config.js
```js
// ecosystem.config.js
module.exports = {
  apps: [
    {
      name: 'myapp',
      script: 'cloudoll',
      args: 'start -n myapp -m production -env prod',
      env: {
        NODE_ENV: 'production',
      }
    }
  ]
}
```
pm2 + docker 
```dockerfile
FROM node:20-slim

RUN apt-get update && \
    apt-get install -y python3 python3-pip && \
    npm install -g pm2

COPY . /app
WORKDIR /app
RUN pip install .

COPY ecosystem.config.js .

CMD ["pm2-runtime", "ecosystem.config.js"]
```
