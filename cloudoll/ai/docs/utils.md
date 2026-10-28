---
title: 工具函数
order: 145
icon: config
---

# 工具函数

`cloudoll.utils` 里是与 Web 层、数据库都无关的小工具：可逆加密、单向摘要、随机字符串、分布式 ID。它们可以在任意脚本里直接导入，不需要 `Application`。

## 可逆加密

需要在之后取回原文时用 `CryFernet`（AES-128-CBC + HMAC，来自 `cryptography` 的 Fernet 令牌格式）。`cryptography` 自 4.5.0 起是基础依赖，装 `cloudoll` 就有，不需要额外 extra：

```python
import os

from cryptography.fernet import Fernet
from cloudoll.utils.password import CryFernet

KEY = os.environ["CLOUDOLL_CRYPTO_KEY"]  # 与数据库密码同级对待，见配置文件

crypt = CryFernet(KEY)
token = crypt.encrypt("sk-abcdef")
assert crypt.decrypt(token) == "sk-abcdef"
```

密钥必须是 32 字节 url-safe base64 编码，新密钥用 `Fernet.generate_key().decode()` 生成，只放在进程环境里，见[配置文件](/config)。构造时密钥不合法会立即报错；换密钥后旧 token 一律解不开（抛 `InvalidToken`），所以轮换要先解密再重新加密。

同一明文每次得到的 token 都不同（内含时间戳和随机 IV），因此 token 不能作为等值判断的键，也不能直接当唯一索引；需要可比较的定长值时用下一节的摘要。

## 单向摘要

```python
from cloudoll.utils.password import hash as keyed_hash

digest = keyed_hash("alice", "pepper")  # sha256("alice" + "pepper") 的十六进制
```

结果是 64 位小写十六进制，同样的输入永远得到同样的结果，适合做幂等键、缓存键、数据指纹。`key` 传 `None` 或空串都表示不加 pepper。

**不要用它存用户密码。** `hash()` 没有盐、没有迭代次数，同一密码的摘要固定，彩虹表和 GPU 暴力破解对它有效；用户密码要用 bcrypt、argon2 这类专用慢哈希（额外依赖由业务引入），框架不内置密码存储方案。

## 随机字符串

```python
from cloudoll.utils.password import generator

make_token = generator(32)  # 返回函数，每次调用给一个新的随机串
make_with_symbols = generator(16, True)

value = make_token()
assert len(value) == 32
```

`generator()` 返回的是生成器函数，不是字符串；字母表默认 `A-Za-z0-9`（62 个字符），`use_special=True` 时追加 `string.punctuation`（共 94 个）。取值用 `secrets`，可用于随机口令、邀请码、临时密钥。强度按字母表规模算：16 位字母数字约 95 bit，需要更高就加长。随机串本身不带校验，要防篡改仍需签名或加密。

## 分布式 ID

```python
from cloudoll.utils.snowflake import IdWorker

worker = IdWorker(worker_id=1, datacenter_id=1)
order_id = worker.next_id()
```

位分配与 Twitter Snowflake 一致：12 位序列号、5 位 `worker_id`、5 位 `datacenter_id`，高位是相对 2010-11-04 的毫秒时间戳。结果是 63 位以内的正整数，可以直接存 BigInt 字段。

- `worker_id`、`datacenter_id` 只接受 0 到 31，越界抛 `ValueError`。
- 一个 `worker_id + datacenter_id` 组合同时只能有一个实例在发号。多进程部署时每个进程都要分到不同编号，否则同一毫秒可能发出相同 ID。
- 单实例内 ID 严格递增，多线程共用同一实例是安全的（内部加锁）。同一毫秒内用完 4096 个序列号后，`next_id()` 会等到下一毫秒再返回。
- 检测到时钟回拨时抛异常，而不是返回可能重复的 ID。NTP 大步回调、虚机时钟漂移都会触发；不能接受异常的业务要自己降级（例如改用数据库序列）。

IdWorker 只负责生成 ID，不做持久去重，也不保证跨实例的全局有序。需要"绝不重复"时给该列加数据库唯一约束，见[数据库](/database)。
