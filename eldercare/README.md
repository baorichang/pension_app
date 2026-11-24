# 养老 App 后端领域服务（Python 首版）

依据 `../PRD.md` 与 `../开发计划.md` 实现的首版 MVP 服务端核心。Python + SQLite，
老人端与子女端基于同一权威数据库同源读写，配套 pytest 测试覆盖各阶段与两端一致性用例。

## 一、运行环境

- Python 3.10+（开发环境 3.13）
- 依赖：`pytest`、`fastapi`、`uvicorn[standard]`、`websockets`（见 `requirements.txt`）

```bash
# 安装依赖
python -m pip install -r requirements.txt

# 在 eldercare 目录下运行全部领域测试
python -m pytest -v
```

## 二、启动浏览器演示服务（HTTP + WebSocket）

在 `eldercare` 目录下：

```bash
# Windows PowerShell
$env:PYTHONPATH="."
python run.py
```

启动后浏览器访问：<http://127.0.0.1:8000>

- 根路径 `/` 即移动端演示页（手机样机样式，可在"老人端 / 子女端"间切换）。
- 演示账号与固定验证码 `123456`（开发期简化，未接真实短信）：

| 端 | 手机号 | 角色 | 初始数据 |
| --- | --- | --- | --- |
| 老人端 | `13300000001` | elder | 王阿姨，68 岁，高血压，青霉素过敏，幸福小区 1 栋 |
| 子女端 | `13300000002` | family | 已绑定上述老人，可查看概览/详情/告警/代付订单 |

- 老人端写入（体征、服药、SOS、本人下单）与子女端写入（代付下单、支付、告警已读）
  都落在同一个服务端 SQLite 主库 `server.db`；变更通过 WebSocket `/ws?user_id=<id>`
  实时推送 `alert_new` / `order_update`，对端页面收到后自动刷新。

### 接口一览（前缀 `/api`）

| 端 | 方法 | 路径 | 用途 |
| --- | --- | --- | --- |
| 公共 | POST | `/api/auth/login` | 验证码登录，返回 user_id / token |
| 公共 | GET | `/api/me` | 当前账号与设置 |
| 老人 | GET/PUT | `/api/profile` | 读取/保存健康档案 |
| 老人 | GET/POST | `/api/vitals` | 体征历史 / 录入体征（触发规则告警） |
| 老人 | GET/POST | `/api/medications` | 用药计划列表 / 添加用药 |
| 老人 | POST | `/api/medications/{plan_id}/taken` | 标记服药状态 |
| 老人 | POST | `/api/sos` | 一键求助，推送全部家属 |
| 老人 | GET/PUT | `/api/sos/settings` | 跌倒/围栏/久坐开关 |
| 老人 | GET | `/api/messages` | 消息列表 |
| 老人 | POST | `/api/messages/{id}/read` | 标记已读 |
| 老人 | GET/PUT | `/api/settings` | 适老化设置 |
| 老人 | GET/POST | `/api/orders` | 本人订单 / 本人下单 |
| 子女 | GET | `/api/family/overviews` | 已绑定老人概览聚合 |
| 子女 | GET | `/api/family/elders/{elder_id}/detail` | 老人详情（体征/用药/订单） |
| 子女 | GET | `/api/family/alerts` | 告警列表 |
| 子女 | POST | `/api/family/alerts/{id}/read` | 告警标记已读/已联系 |
| 子女 | GET/POST | `/api/family/orders` | 代付订单 / 子女代付下单 |
| 子女 | POST | `/api/family/orders/{id}/pay` | 家属支付，回写订单状态机 |
| 公共 | GET | `/api/resources?category=` | 服务资源浏览 |
| 公共 | GET | `/api/sync/changes?since=` | 增量变更拉取 |
| 公共 | GET | `/api/health` | 健康检查 |
| WebSocket | WS | `/ws?user_id=<id>` | 实时推送告警/订单变更 |

> 演示期 HTTP 认证简化为请求头 `X-User-Id: <user_id>`；生产环境应替换为真实登录 token 校验。

## 三、目录结构

```
eldercare/
├── app/
│   ├── db.py            # SQLite 连接、建表、时间戳/版本、变更日志
│   ├── models.py         # 角色、状态、告警/订单/授权等常量枚举
│   ├── errors.py        # 业务异常与统一响应结构
│   ├── auth.py          # 验证码登录、会话 token、角色识别
│   ├── bindings.py      # 亲属多对多绑定/解绑与访问权限校验
│   ├── profile.py       # 老人健康档案（覆盖型，last-write-wins）
│   ├── health.py        # 体征记录、用药计划与服药记录（追加型）
│   ├── sos.py           # 一键 SOS、紧急联系人、安全开关
│   ├── alerts.py        # 告警规则生成、家属视角列表、已读状态
│   ├── family.py        # 家属概览/详情聚合（绑定鉴权后读同源数据）
│   ├── resources.py     # 居家/社区/机构服务资源（两端只读）
│   ├── orders.py        # 订单创建、本人付/家属代付、服务端状态机
│   ├── messages.py      # 消息通知与已读状态
│   ├── consents.py      # 隐私授权开启/撤回
│   ├── settings.py      # 适老化设置（字体/播报/对比度/语音输入）
│   ├── speech.py         # 语音转写与播报文本占位
│   ├── offline.py       # 客户端本地待同步补偿队列
│   ├── sync.py          # 增量拉取、离线补传、一致性规则
│   └── web/             # HTTP/WebSocket 接口层与浏览器演示页
│       ├── deps.py      # 服务端 SQLite 连接、初始化、演示种子数据
│       ├── push.py      # WebSocket 推送注册表（按用户/家属/老人广播）
│       ├── routes.py     # FastAPI 路由与请求模型
│       ├── main.py      # 应用组装、异常处理、静态页、/ws 端点
│       └── static/index.html  # 移动端单页演示（原生 JS，可切换两端）
└── tests/
    ├── conftest.py                     # 独立临时 SQLite 库夹具
    ├── test_stage0_db.py               # 阶段 0：建表与基础约束
    ├── test_stage1_auth_bind.py        # 阶段 1：认证、绑定、权限
    ├── test_stage2_health_sos.py       # 阶段 2：档案/健康/用药/SOS/队列
    ├── test_stage3_family_alert.py     # 阶段 3：家属概览/详情/告警
    ├── test_stage4_resource_order.py  # 阶段 4：资源/订单状态机
    ├── test_stage5_message_consent_setting.py  # 阶段 5：消息/授权/设置/语音
    ├── test_stage6_consistency.py     # 阶段 6：T-C1 ~ T-C14 一致性专项
    ├── test_stage7_vital_source.py     # 问题 1：手动/智能设备录入来源
    ├── test_stage8_vital_entry.py     # 问题 2：按类型点击录入与过滤
    ├── test_stage9_server_time.py      # 问题 3：操作时间取服务端系统时间
    ├── test_stage10_login_ui.py       # 问题 4：登录界面要素与链路
    ├── test_stage11_prototype.py      # 问题 5：导航/分类/入口对齐原型
    ├── test_stage12_badge.py          # 问题 6：未读消息/告警角标计数
    └── test_stage13_ui_polish.py       # 界面细化：下拉/状态中文/状态栏/AI 助手
```

## 四、已实现模块（对应开发计划阶段）

| 阶段 | 模块 | 能力 |
| --- | --- | --- |
| 0 | 数据库底座 | 12+2 张核心表，时间戳、版本号、变更日志、外键与 CHECK 约束 |
| 1 | 认证与绑定 | 验证码登录（开发期固定码 `123456`）、token 会话、多对多绑定/解绑、家属访问鉴权 |
| 2 | 老人端核心 | 档案、体征录入与历史、用药计划与服药标记、SOS 求助与安全开关、离线队列 |
| 3 | 子女监护 | 老人概览/详情聚合、SOS 与规则告警、告警列表与已读回写 |
| 4 | 资源与订单 | 三类资源浏览详情、下单、本人付/家属代付、订单状态机、两端同源订单查询 |
| 5 | 消息/授权/设置 | 消息分类与已读、隐私授权开启撤回、适老化设置、语音能力占位 |
| 6 | 同步一致性 | 增量拉取、离线补传、幂等去重、冲突规则、14 条一致性用例 |

## 五、两端数据一致性设计

1. **服务端唯一权威**：所有业务数据存 SQLite 主库；客户端本地仅存缓存、离线副本与待同步队列。
2. **两端同源同接口**：老人端与子女端调用同一套领域方法、读同一批表，家属端不维护独立副本。
3. **先落库再下发**：写入先在服务端落库并记录 `change_log`，再由增量拉取/推送同步到对端。
4. **增量同步**：`sync.pull_changes(since)` 按 `changed_at` 游标返回新变更；进入前台/网络恢复时拉取兜底。
5. **离线补偿**：断网写入进入 `OfflineQueue`，联网后按序补传；凭幂等键去重，重试不产生重复记录。
6. **冲突规则**：
   - 档案/设置等覆盖型数据：服务端最新为准（last-write-wins）。
   - 体征/服药/告警/消息等追加型数据：只追加，不被旧记录覆盖。
   - 订单状态：只能由服务端状态机流转，调用方提交动作，不能直接改状态。
7. **权限跟随绑定**：绑定即授权，解绑即收回；家属只能访问已绑定且授权的老人数据。

## 六、一致性测试用例（T-C1 ~ T-C14）

| 编号 | 场景 | 编号 | 场景 |
| --- | --- | --- | --- |
| T-C1 | 档案两端一致 | T-C8 | 解绑后权限收回 |
| T-C2 | 体征同步 | T-C9 | 断网补传不重复 |
| T-C3 | 服药状态同步 | T-C10 | 离线副本可读 |
| T-C4 | SOS 告警同步 | T-C11 | 增量拉取只取新变更 |
| T-C5 | 规则告警同步 | T-C12 | 冲突不回退 |
| T-C6 | 代付订单两端一致 | T-C13 | 已读状态一致 |
| T-C7 | 订单状态同步 | T-C14 | 多家属数据一致 |

## 七、占位与边界（首版未接入）

- 短信为开发期固定验证码，未接真实短信服务。
- 语音转写/播报、地图定位为占位接口，未接第三方 SDK。
- 首版"手机 App"以浏览器移动端演示页呈现，尚无原生 Android/iOS 安装包；HTTP 认证为演示简化（`X-User-Id` 头），未接真实 token/会话服务。
- 护工端、机构/社区后台、运营后台、智能设备接入、在线问诊闭环、社交商城等按 PRD 第 8 章延后。

## 八、测试结果

当前全量 **88 个用例全部通过**（阶段 0–6 一致性专项 + 问题 1–6 专项 + 界面细化专项）。运行：

```bash
python -m pytest -v
```
