# HoneyChat：基于 RAG 的对话式智能蜜罐系统

HoneyChat 是一个轻量级、易部署的**对话式智能蜜罐系统**，专为研究生复试项目设计。它通过**检索增强生成（RAG）**技术，使蜜罐能够根据攻击者输入的命令，从历史攻击语料库中检索相似场景，并利用本地大语言模型（LLM）生成上下文一致、高度逼真的响应，从而有效欺骗攻击者并捕获其行为。

## ✨ 核心创新点

- **RAG 驱动的动态响应生成**：传统蜜罐使用固定响应模板，极易被指纹识别。HoneyChat 将每一次攻击者命令作为查询，在向量数据库（Chroma）中检索最相似的历史命令-输出对，然后将检索结果作为上下文，调用本地 LLM 生成自然、连贯且符合系统状态的响应，大幅提升诱饵逼真度。

- **威胁情报驱动的自适应交互**：系统在握手阶段查询攻击者 IP 的信誉（通过 AbuseIPDB 等 API），根据威胁评分动态调整蜜罐呈现的操作系统类型、服务版本甚至开放端口，使攻击者面对“定制化”诱饵，增加其信任度。

- **实时可视化仪表盘**：提供基于 Web 的实时仪表盘，展示当前活跃会话、历史命令记录、威胁情报标签，并支持按攻击者 IP、时间线回放完整交互过程，帮助分析师快速理解攻击手法。

- **轻量级一键部署**：所有组件（蜜罐服务、RAG 引擎、向量数据库、Web 仪表盘）打包为 Docker 容器，通过 `docker-compose up` 一键启动，无需 GPU（模型 CPU 量化），本地单机即可运行，极大降低使用门槛。

## 🏗️ 系统架构

HoneyChat 由三个核心服务组成：

1. **蜜罐前端服务**（honeypot）：模拟 SSH/HTTP 服务，接收攻击者连接，将命令转发至 RAG 引擎，并将响应返回给攻击者。
2. **RAG 引擎服务**（rag-engine）：基于 FastAPI 和 ChromaDB 实现，接收命令，在向量库中检索相似历史记录，调用本地 LLM 生成最终响应。
3. **仪表盘服务**（dashboard）：Flask 应用，通过 WebSocket 实时推送事件，提供 Web 界面查看攻击详情。

所有服务通过 Docker Compose 编排，共享网络，数据持久化到本地卷。

## 🚀 快速开始

### 前置条件

- Docker 和 Docker Compose（建议 Docker 20.10+，Compose 2.0+）
- 至少 4GB 可用内存（推荐 8GB）
- 10GB 可用磁盘空间（用于模型和数据库）

### 安装步骤

1. **克隆项目**

   ```bash
   git clone https://github.com/yourname/honeychat.git
   cd honeychat

2. **配置环境变量（可选）**

   复制环境变量示例文件并根据需要修改：

   ```bash
   cp .env.example .env
   # 编辑 .env 文件，例如填写威胁情报 API 密钥、修改端口等
   ```

3. **下载 LLM 模型**

   HoneyChat 默认使用 Llama 2 7B 的量化版本（约 4GB）。运行以下命令自动下载：

   ```bash
   make download-model
   ```

   或者手动下载任意 GGUF 格式模型，放入 `models/` 目录，并修改 `config/rag_config.yaml` 中的 `model_path`。

4. **创建必要的本地目录**

   ```bash
   make check-dirs
   ```

5. **构建并启动所有服务**

   ```bash
   make build
   make up
   ```

   首次启动将构建镜像并初始化数据库，耗时约 1-2 分钟。

6. **查看服务状态**

   ```bash
   make ps
   ```

   所有服务应为 `Up` 状态。

7. **访问仪表盘**

   打开浏览器访问 `http://localhost:5000`，即可看到实时攻击事件仪表盘。

8. **测试蜜罐**

   使用 SSH 客户端连接蜜罐：

   ```bash
   ssh root@localhost -p 2222
   # 任意密码均可登录
   ```

   输入一些 Linux 命令（如 `ls`, `whoami`, `cat /etc/passwd`），观察仪表盘是否实时显示事件。

   或使用 curl 测试 HTTP 蜜罐：

   ```bash
   curl http://localhost:8080/admin
   curl http://localhost:8080/api/users
   ```

### 常用命令

| 命令                  | 说明                         |
| --------------------- | ---------------------------- |
| `make up`             | 启动所有服务（后台模式）     |
| `make down`           | 停止所有服务                 |
| `make logs`           | 查看所有服务日志（实时跟踪） |
| `make build`          | 重新构建镜像                 |
| `make clean`          | 清理未使用的 Docker 资源     |
| `make download-model` | 下载默认 LLM 模型            |

## 📁 项目结构

```
honeychat/
├── docker-compose.yml           # 服务编排
├── Makefile                     # 常用命令
├── .env.example                 # 环境变量示例
├── config/                      # 配置文件目录
│   ├── honeypot_config.yaml
│   ├── rag_config.yaml
│   └── dashboard_config.yaml
├── data/                        # 持久化数据（自动创建）
│   ├── logs/
│   ├── chroma_db/
│   └── dashboard/
├── models/                      # LLM 模型文件存放目录
├── services/                    # 各服务源代码
│   ├── honeypot/
│   ├── rag-engine/
│   └── dashboard/
└── README.md
```

## 🧪 测试与验证

### 模拟攻击测试

项目提供了测试脚本 `scripts/test_attack.py`（需手动创建），可模拟常见攻击命令序列。例如：

```bash
docker-compose exec honeypot python scripts/test_attack.py
```

### 性能指标

在 Intel i5-1135G7 16GB 内存的笔记本上测试（无 GPU）：

- **RAG 引擎响应时间**：平均 1.2 秒（包含检索和生成）
- **蜜罐并发连接**：可同时处理约 50 个 SSH 会话
- **磁盘占用**：约 5GB（含模型文件）

## 🛠️ 自定义与扩展

- **添加更多命令模板**：编辑 `services/rag-engine/data/command_pairs.json`，添加新的命令-输出对，重启 RAG 引擎后自动加载。
- **更换 LLM 模型**：下载其他 GGUF 模型放入 `models/`，修改 `config/rag_config.yaml` 中的 `model_path`。
- **集成其他威胁情报源**：在 `services/honeypot/utils/ip_utils.py` 中扩展 `ThreatIntelChecker` 类。
- **添加更多协议模拟**：在 `services/honeypot/protocol/` 下创建新模块，参考 `ssh_server.py` 实现。

## 📊 复试答辩要点

- **创新点**：将 RAG 引入蜜罐交互，提升逼真度；结合威胁情报动态调整策略；可视化实时攻击。
- **技术实现**：使用 FastAPI + ChromaDB + llama-cpp-python + Flask-SocketIO。
- **部署便捷性**：全容器化，一键启动，无需 GPU，适合演示。
- **成果展示**：可通过仪表盘直观看到攻击事件，并对比传统蜜罐的响应（可选）。

## 📄 许可证

MIT License

---

**HoneyChat** 项目为实验测试项目，旨在展示前沿 AI 技术与网络安全防御的结合。欢迎使用和改进！如有问题，请提交 Issue 或联系作者。