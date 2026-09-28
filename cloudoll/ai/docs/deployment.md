---
title: 部署
order: 180
icon: deployment
---

# 应用部署

## 生产启动与 CLI 边界

在应用根目录创建虚拟环境、安装经过验证并锁定版本的 requirements.txt：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/cloudoll start -n myapp -env prod -m production
```

生产模式前台运行，没有开发热重载，也不是带崩溃自动重启的守护进程。CLI 提供进程身份/锁校验与手动管理：

```sh
cloudoll list
cloudoll stop -n myapp
cloudoll restart -n myapp
```

服务名使用以 ASCII 字母/数字开头、只含字母数字下划线连字符的名称，长度不超过 64，避免 Windows 保留名。每个实例使用独立名称、端口或 Unix socket。

旧版仅含 PID 的文件无法证明进程身份，不能安全按 PID 自动接管。升级时先核实并正常停止旧服务，再用新 CLI 启动，生成完整身份记录；不要仅删锁文件后重复启动，更不要按不确定 PID 强杀。

## Supervisor

Cloudoll 的生产前台模式可交给 Supervisor。不要使用 nohup、后台 & 或开发模式；Supervisor 要求受管子进程保持前台运行。参见[官方子进程说明](https://supervisord.org/subprocess.html)。

下面为单实例示例。预先准备 app 用户、项目、虚拟环境和可写日志目录；路径需按部署调整：

```ini
[program:myapp]
directory=/srv/myapp
command=/srv/myapp/.venv/bin/cloudoll start -n myapp -m production -env prod --host 127.0.0.1 --port 9001
user=app
environment=HOME="/home/app",CLOUDOLL_LOG_DIR="/var/log/myapp"
autostart=true
autorestart=true
startsecs=5
startretries=3
stopsignal=TERM
stopwaitsecs=90
stopasgroup=true
killasgroup=true
redirect_stderr=true
stdout_logfile=/var/log/myapp/supervisor.log
stdout_logfile_maxbytes=20MB
stdout_logfile_backups=3
```

user 不会自动更正 HOME 等环境，示例因此显式设置。业务密钥由部署环境安全注入，确保 supervisord 启动时能够继承。参数含义见[官方配置说明](https://supervisord.org/configuration.html)。

由 Supervisor 管理时统一使用 `supervisorctl stop myapp` / `supervisorctl restart myapp`，不要同时使用 cloudoll stop/restart，否则 Supervisor 可能把人为停止当成异常退出后重新拉起。CLI 不替代 Supervisor 的自动重启和进程组管理。

停止期限要按各层协调：原生数据库池 close_timeout 默认 10 秒，server.resource_close_timeout/resource_shutdown_timeout 默认 10/30 秒；总进程退出还包含请求排空和用户钩子，不能只按 30 秒计算。上例 stopwaitsecs=90 只是起点，应按实际应用验证。Cloudoll 自身 stop 命令还有独立的强制停止期限，不应代替 Supervisor 的管理入口。详见[生命周期](/app-start)。

多实例可复制 program 块，分别改 program 名、-n 名称、端口和日志。所有实例共享 Session 密钥，按需共享 Redis；每个实例的数据库池连接数会累计，需核对数据库上限。

## Nginx

下面是同机 HTTP 反向代理配置，生产公网还需要 TLS：

```nginx
upstream cloudoll_app {
    server 127.0.0.1:9001;
}

server {
    listen 80;
    server_name example.com;
    client_max_body_size 10m;

    location / {
        proxy_pass http://cloudoll_app;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /srv/myapp/static/;
        autoindex off;
    }

    location /events {
        proxy_pass http://cloudoll_app;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_read_timeout 75s;
        proxy_set_header Host $host;
    }
}
```

静态 alias 指向真实目录，不要重复拼接 static。SSE 超时需配合业务心跳；WebSocket 使用[专用代理设置](/websockets)。不要无条件信任互联网请求传来的 X-Forwarded-*，只接受可信代理链并按业务需求解析。

## 容器

单进程容器可直接前台运行 Cloudoll，由容器平台负责重启，不必再套一层 Supervisor。基础示例：

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --create-home app
COPY --chown=app:app . .
USER app
EXPOSE 9001
CMD ["cloudoll", "start", "-n", "myapp", "-m", "production", "-env", "prod", "--host", "0.0.0.0", "--port", "9001"]
```

生产锁定经过测试的包版本和镜像摘要，配置 .dockerignore 排除虚拟环境、开发配置、密钥与上传文件。config/conf.prod.yaml 可只引用运行时环境变量，或由部署系统挂载；不要把真实密钥 COPY 进镜像。

该 CMD 使用 exec 形式以便传递停止信号。容器/平台的停止宽限期需要覆盖请求和资源关闭时间。按需要挂载日志与上传卷，限制磁盘占用；CLI 默认还会写文件日志，不是仅输出 stdout。

## 上线前

- 确认部署使用 Cloudoll 4.1.0，并按升级说明完成配置与 API 迁移。
- 设置独立 JWT 密钥、共享 Session 密钥，HTTPS 下启用安全 Cookie。
- 关闭 SQL 参数日志，校验数据库 TLS、最小权限账号及连接池总量。
- 准备健康检查、备份恢复、错误告警和停止/重启演练。
- 配置文件必须实际存在且关键环境变量齐全；验证旧 Token 在新的 exp/issuer/audience 策略下的迁移。
- 按需使用 JSON 日志、脱敏和[监控扩展](/logs)，不要把 SQL 参数或完整 Token 发到日志平台。
- Aurora 仍未验证，不能套用原生数据库的通过结果宣称可生产上线。
