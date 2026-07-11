# ai-education-chatbot
使用 Rasa Pro Flow 模式构建的智能订单对话系统，支持订单查询、修改收货信息、取消订单等核心功能。基于 Python + Rasa SDK 开发自定义 Action，通过 SQLAlchemy 操作 MySQL 数据库，实现订单信息的查询与更新。设计了完整的对话状态管理机制，包括槽位预填充、状态流转（receive_id: modify→modified）等核心逻辑。实现了省市区三级联动选择功能，通过数据库查表动态生成可选按钮列表。系统采用环境变量管理敏感配置，确保密钥安全。项目包含完整的使用文档和代码注释，具备良好的可维护性和扩展性。
