# 智能订单助手（基于 Rasa Pro）

一个基于 Rasa Pro 构建的智能订单对话系统，支持订单查询、修改收货信息、取消订单等核心功能。

## 技术栈

- **框架**: Rasa Pro 3.x (Flow 模式)
- **语言**: Python 3.11+
- **数据库**: MySQL 5.7+
- **ORM**: SQLAlchemy 2.x
- **LLM**: 阿里云通义千问 (qwen-turbo)

## 项目结构

```
rasa_ecs_0319/
├── actions/                    # 自定义 Action 实现
│   ├── __init__.py             # 包初始化文件
│   ├── action_order.py         # 订单相关 Action（核心）
│   ├── action_logistics.py     # 物流相关 Action
│   ├── action_postsale.py      # 售后相关 Action
│   ├── action_template.py      # Action 模板
│   ├── db.py                   # 数据库连接配置
│   └── db_table_class.py       # 数据库表 ORM 映射类
├── data/
│   └── flows/                  # Flow 流程定义
│       ├── flow_order.yml      # 订单流程（核心）
│       ├── flow_logistics.yml  # 物流流程
│       ├── flow_postsale.yml   # 售后流程
│       └── flow_patterns.yml   # 模式匹配流程
├── domain/                     # 域配置
│   ├── domain_order.yml        # 订单域定义（槽、响应、Action）
│   ├── domain_logistics.yml    # 物流域定义
│   ├── domain_postsale.yml     # 售后域定义
│   └── domain_patterns.yml     # 模式匹配域定义
├── e2e_tests/                  # 端到端测试
├── models/                     # 训练好的模型
├── .env                        # 环境变量配置
├── .gitignore                  # Git 忽略规则
├── config.yml                  # Rasa 配置文件
├── credentials.yml             # 渠道凭证配置
├── endpoints.yml               # 端点配置
└── ecs.sql                     # 数据库初始化脚本
```

## 核心功能

### 1. 订单查询
- 支持多种条件筛选：
  - 已发货订单
  - 已发货/已签收订单
  - 进行中或3日内完成的订单
  - 已签收之前状态的订单
  - 已发货之前状态的订单
  - 已签收及之后状态的订单

### 2. 修改订单收货信息
- 选择现有收货信息或新建
- 支持修改收货人姓名、联系电话、收货地址
- 省市区三级联动选择
- 支持多次修改不同字段
- 收货信息去重机制

### 3. 取消订单
- 支持待支付/待发货状态的订单取消
- 待发货订单取消后自动提示退款信息

## 快速开始

### 环境要求

- Python 3.11+
- MySQL 5.7+
- Rasa Pro 3.x
- 阿里云通义千问 API Key

### 安装步骤

1. **克隆项目**

2. **创建虚拟环境**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # 或
   venv\Scripts\activate     # Windows
   ```

3. **安装依赖**
   ```bash
   pip install rasa-pro sqlalchemy pymysql python-dotenv
   ```

4. **配置环境变量**
   ```bash
   cp .env.example .env
   ```
   
   编辑 `.env` 文件，配置以下内容：
   ```env
   # LLM 配置
   LLM_API_HEALTH_CHECK=true
   API_KEY=your-qwen-api-key

   # 数据库配置
   DB_HOST=localhost
   DB_PORT=3306
   DB_NAME=ecs
   DB_USER=root
   DB_PASSWORD=your-db-password
   ```

5. **初始化数据库**
   ```bash
   mysql -u root -p < ecs.sql
   ```

### 运行项目

1. **启动 Action Server**
   ```bash
   rasa run actions
   ```

2. **启动 Rasa Pro**
   ```bash
   rasa shell
   ```

### 训练模型

```bash
rasa train
```

## 核心 Action 说明

### AskOrderID
- **功能**: 查询订单列表，返回按钮供用户选择
- **槽依赖**: `user_id`, `goto`
- **输出**: `order_id` 槽值

### GetOrderDetail
- **功能**: 获取并展示订单完整信息
- **槽依赖**: `order_id`
- **输出**: 订单详情消息（含订单明细、收货信息、物流信息、售后信息）

### AskReceiveId
- **功能**: 查询用户现有收货信息，返回选择按钮
- **槽依赖**: `user_id`, `order_id`
- **输出**: 预填充的收货信息槽值（`receiver_name`, `receiver_phone`, `receive_province` 等）

### AskSetReceiveInfo
- **功能**: 设置订单收货信息，支持新建和使用现有信息
- **槽依赖**: `receive_id`, `set_receive_info`, `order_id`, `user_id`, 收货信息相关槽
- **输出**: 数据库更新操作

### CancelOrder
- **功能**: 取消订单
- **槽依赖**: `order_id`
- **输出**: 订单状态更新为"已取消"

## Flow 流程说明

### 修改订单收货信息流程

```
1. set_slots(goto=action_ask_order_id_before_delivered)
       ↓
2. collect(order_id) → 用户选择订单
       ↓
3. action_get_order_detail → 查询订单详情
       ↓
4. collect(receive_id) → 选择收货信息操作
       ├── "false" → END
       ├── "modify" → 进入修改流程
       └── 其他 → 使用现有收货信息
       ↓
5. select_modify_content → 选择修改内容（姓名/电话/地址）
       ↓
6. collect(对应字段) → 收集修改内容
       ↓
7. if_modify_continue → 询问是否继续修改
       ├── true → set_slots(receive_id=modified) → 回到步骤5
       └── false → 进入确认
       ↓
8. confirm_receive_info → 确认修改
       ├── true → action_ask_set_receive_info → 执行入库
       └── false → END
```

## 槽位定义

| 槽名 | 类型 | 说明 |
|------|------|------|
| `goto` | text | 查询条件标志位 |
| `order_id` | text | 订单ID |
| `receive_id` | text | 收货信息ID（modify/modified/具体ID） |
| `receiver_name` | text | 收货人姓名 |
| `receiver_phone` | text | 联系电话 |
| `receive_province` | text | 收货省份 |
| `receive_city` | text | 收货城市 |
| `receive_district` | text | 收货城区 |
| `receive_street_address` | text | 详细街道地址 |
| `modify_content` | text | 修改内容选择 |
| `if_modify_continue` | bool | 是否继续修改 |
| `set_receive_info` | bool | 是否确认修改 |

## 数据库表结构

### 核心表

| 表名 | 说明 |
|------|------|
| `order_info` | 订单主表 |
| `order_detail` | 订单明细表 |
| `order_status` | 订单状态表 |
| `receive_info` | 收货信息表 |
| `region` | 省市区表 |
| `logistics` | 物流信息表 |
| `postsale` | 售后信息表 |

## 配置文件说明

### .env 文件
存放敏感配置信息，如数据库连接、API Key 等。**不要提交到版本控制**。

### config.yml
Rasa Pro 配置文件，包含 pipeline、policies、assistant_id 等配置。

### endpoints.yml
端点配置文件，包含 action_endpoint、nlg、model_groups 等配置。

### credentials.yml
渠道凭证配置文件，用于配置连接到外部聊天平台（如 REST API）。

## 开发规范

### Action 开发规范

1. **类名**: 使用 PascalCase 命名，如 `AskOrderID`
2. **name() 方法**: 返回值必须与 domain 中定义的 Action 名称一致
3. **run() 方法**: 接收 `dispatcher`, `tracker`, `domain` 参数，返回事件列表
4. **数据库操作**: 使用 `SessionLocal()` 创建会话，通过 `with` 语句自动管理生命周期

### 槽位命名规范

1. 使用 snake_case 命名，如 `order_id`
2. 布尔类型槽使用 `if_` 前缀，如 `if_modify_continue`
3. 状态标记槽使用描述性名称，如 `receive_id`

### 代码注释规范

1. 模块级注释：说明模块功能和技术栈
2. 类级注释：说明类的功能和使用场景
3. 方法级注释：说明方法的功能、参数和返回值
4. 关键逻辑注释：说明复杂逻辑的实现思路

## 测试

### 端到端测试

```bash
rasa test e2e
```

### 单元测试

项目暂未提供单元测试，建议为核心 Action 添加测试用例。

## 部署

### 开发环境

```bash
rasa shell
```

### 生产环境

```bash
# 启动 Action Server（后台运行）
nohup rasa run actions > actions.log 2>&1 &

# 启动 Rasa Pro 服务
nohup rasa run --enable-api --cors "*" > rasa.log 2>&1 &
```

## 常见问题

### Q: 数据库连接失败？
A: 检查 `.env` 文件中的数据库配置，确保 MySQL 服务已启动，且数据库用户有访问权限。

### Q: Action 找不到？
A: 确保 Action 的 `name()` 方法返回值与 `domain_order.yml` 中定义的名称一致。

### Q: 槽值没有正确更新？
A: 检查槽的映射类型是否正确（`controlled` 或 `from_llm`），确保通过 `SlotSet` 或 `/SetSlots()` 设置槽值。

### Q: LLM 调用失败？
A: 检查 `API_KEY` 是否正确配置，确保网络能访问阿里云 API。

## 许可证

MIT License

## 作者

智服在线项目组

## 版本历史

- v1.0.0: 初始版本，支持订单查询、修改收货信息、取消订单功能