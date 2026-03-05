```
honeychat/
├── docker-compose.yml              # 主编排文件
├── .env.example                     # 环境变量示例
├── Makefile                         # 常用命令（build, up, down, logs）

├── services/
│   ├── honeypot/                     # 蜜罐前端服务
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── honeypot_server.py        # 主程序：启动SSH/TCP服务，处理连接
│   │   ├── protocol/
│   │   │   ├── ssh_server.py         # SSH协议实现（基于paramiko）
│   │   │   └── tcp_server.py         # 简单TCP服务（用于HTTP/Telnet模拟）
│   │   ├── handler.py                 # 连接处理逻辑：接收命令，调用RAG API
│   │   ├── config.py                  # 配置（监听端口、RAG引擎地址等）
│   │   └── utils/
│   │       └── ip_utils.py            # IP解析、威胁情报查询（调用外部API）
│   │
│   ├── rag-engine/                    # RAG引擎服务（FastAPI）
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app.py                      # FastAPI应用，提供 /generate 端点
│   │   ├── rag/
│   │   │   ├── __init__.py
│   │   │   ├── vector_store.py         # Chroma向量库封装（加载/检索）
│   │   │   ├── llm_wrapper.py          # LLM加载与生成（GPT4All/llama.cpp）
│   │   │   └── prompt_templates.py     # 提示词模板
│   │   ├── data/
│   │   │   └── command_pairs.json      # 预训练命令-输出对（用于构建向量库）
│   │   └── scripts/
│   │       └── build_index.py           # 初始化向量库脚本
│   │
│   ├── dashboard/                       # Web仪表盘（Flask + Socket.IO）
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── app.py                        # 主应用，提供Web界面和API
│   │   ├── models.py                      # SQLAlchemy模型（会话、事件）
│   │   ├── static/                         # CSS/JS
│   │   ├── templates/                      # HTML模板
│   │   │   └── index.html
│   │   ├── socket_events.py                # WebSocket事件处理
│   │   └── config.py
│   │
│   └── nginx/                              # （可选）反向代理，统一入口
│       ├── Dockerfile
│       └── nginx.conf

├── data/                                   # 持久化数据（挂载卷）
│   ├── chroma_db/                           # 向量数据库文件
│   ├── dashboard/                            # SQLite数据库
│   │   └── events.db
│   └── logs/                                 # 蜜罐原始日志

├── scripts/                                 # 辅助脚本
│   ├── download_model.sh                     # 下载LLM模型文件
│   ├── seed_data.py                          # 向向量库填充初始语料
│   └── test_attack.py                        # 模拟攻击测试脚本

├── tests/                                   # 单元测试
│   ├── test_rag.py
│   └── test_honeypot.py

└── README.md                                # 项目说明、快速开始、复试演示指引
```

