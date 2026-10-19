---
title: 邮件
order: 135
icon: router
---

# 发送邮件

`cloudoll.mail.smtp.Client` 是一个直白的 SMTPS 发信客户端，用于告警、报表这类自己拼装正文的场景。它不依赖 `Application`，也不读取 `config/conf.*.yaml`；连接参数由调用方传入，可以放在进程环境或自己的配置里。

库只提供发送，不提供收取邮件，也没有队列、定时与重试。需要投递保障时，把发信交给业务侧重试队列或专业邮件服务。

## 用法

```python
from cloudoll.mail import smtp

client = smtp.Client(
    smtp_server="smtp.example.com",
    account="alert@example.com",
    account_name="监控告警",
    password="授权码",          # 邮箱服务商签发的发信授权码，不是登录密码
    port=465,
)
client.subject = "磁盘使用率超过 90%"
client.content = "host: db-01\nused: 92%"
client.add_to_addr("运维", "ops@example.com")
client.add_to_addr("张三", "zhangsan@example.com")
client.send()
```

构造函数不碰网络，只保存参数；连接和登录发生在 `send()`。因此可以在模块导入时创建客户端，也可以反复用同一个客户端发信——每次 `send()` 都会新建一条连接并在结束时关闭。

## 配置项

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `smtp_server` | 必填 | SMTP 主机名，缺失时构造即抛 `ValueError`。 |
| `port` | `465` | 端口，始终用 `SMTP_SSL` 连接。 |
| `account` | `""` | 登录账号，同时作为发件地址。 |
| `account_name` | `""` | 显示在 `From` 里的发件人名称，支持中文。 |
| `password` | `""` | 发信授权码。账号或授权码为空时 `send()` 抛 `KeyError`，不会先连服务器。 |
| `debug_level` | `0` | 透传 `smtplib.SMTP.set_debuglevel()`，非 0 时把 SMTP 会话过程打到标准输出，其中含登录交互，只在本机排查时开启。 |

只支持 465 端口的隐式 TLS（SMTPS）。587 的 STARTTLS 升级方式没有实现，需要时改用 `smtplib` 自己发送。

## 收件人、正文与附件

`add_to_addr(名称, 地址)` 可以调用多次，它们同属一条邮件的收件人列表；地址为空抛 `KeyError`。`content` 是正文，正文类型由 `mime_type` 决定，默认 `plain`，改成 `"html"` 后正文按 HTML 发送。

```python
client.mime_type = "html"
client.content = "<h1>周报</h1><p>见附件</p>"
client.addfile("/data/report.pdf")
```

`addfile(路径)` 接收绝对路径，按文件名猜测 MIME 类型（猜不到时按 `application/octet-stream`），读取内容并做 Base64 编码。每个附件依次拿到从 0 开始的 Content-ID，可直接内嵌进 HTML 正文：

```python
client.addfile("/data/img/logo.png")    # cid:0
client.addfile("/data/img/chart.png")   # cid:1
client.mime_type = "html"
client.content = '<img src="cid:0"><img src="cid:1">'
```

`addhtml(html)` 是另附一个 HTML 部分，与设置 `mime_type = "html"` 不同：前者正文里同时存在纯文本和 HTML 两个部分，后者只有 HTML 一个部分。标题和正文用普通属性赋值即可，中文无需手工编码。

## 失败与重发

`send()` 不吞异常，登录失败、连接中断、收件人被拒都会原样抛出 `smtplib` / `ssl` 的异常，由调用方决定是否重试。发送中途失败时连接同样会关闭，客户端可以继续复用。

重复调用 `send()` 发送的是标题、正文、收件人和附件的当前快照：改动 `content` 后再发，下一封就是新内容，不会把上一封的正文带过来。附件部分会随客户端保留，重发时仍在。

密钥按快速开始的做法从环境注入，不要把授权码写进仓库。批量投递请在业务侧控制节奏，遵守所用服务商的发信频率限制。
