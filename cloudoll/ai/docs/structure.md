---
title: 目录结构
order: 20
icon: structure
---

# 目录结构

下面是一种包含可选目录的项目布局，不要求每个项目都有所有文件：

```text
myapp/
├── app.py                   # 可选：生命周期钩子 / 脚本入口
├── config/
│   ├── conf.local.yaml
│   └── conf.prod.yaml
├── controllers/
│   ├── __init__.py
│   └── users.py             # 路由
├── middlewares/
│   ├── __init__.py
│   └── auth.py              # 中间件
├── services/
│   ├── __init__.py
│   └── users.py             # 自行组织的业务代码
├── models.py                # ORM 模型
├── templates/               # Jinja2 模板
├── static/                  # 可选静态文件
└── requirements.txt
```

## 自动发现与导入

创建应用时递归扫描 `middlewares` 和 `controllers` 中的 Python 文件；`__init__.py` 不作为独立路由文件扫描。建议各级包保留该文件。不要在控制器导入阶段访问数据库连接，连接要到启动阶段才建立。

当前实现按应用生成独立模块命名空间，避免不同项目的同名 controllers 相互污染；不再把项目目录随意插入全局 `sys.path`。自动发现的模块使用相对导入：

```python
# controllers/users.py
from ..services.users import find_user
from cloudoll.web import get

@get("/users/{id}")
async def user_detail(request):
    return await find_user(request.app.db.mysql, int(request.params.id))
```

上例仅展示目录导入，实际请求应按[路由文档](/router)校验 id。对应业务模块：

```python
# services/users.py
from ..models import User

async def find_user(db, user_id):
    user = await User.use(db).where(User.id == user_id).one_model()
    return user.to_dict(exclude_unset=True) if user is not None else None
```

`models.py` 中的 User 定义见[数据库](/database)。如果路由位于 `controllers/users/index.py`，到根目录 models 的相对导入是 `from ...models import User`。

服务模块不会因为放进 services 就自动注入，需要显式导入。不要直接用 `python controllers/users.py` 启动被扫描的模块。

## 应用根目录

CLI 默认以启动时工作目录作为应用根目录；配置、模板、静态文件和模块发现都相对于它解析。部署时设置工作目录，脚本方式可使用 `Application(root=...)` 明确指定。不要依赖修改全局工作目录来切换同进程中的应用。
