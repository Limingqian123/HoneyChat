# HoneyChat：基于 RAG 的对话式智能蜜罐系统

HoneyChat 是一个轻量级、易部署的**对话式智能蜜罐系统**，利用**检索增强生成（RAG）**技术，使蜜罐能够根据攻击者输入的命令，从历史攻击语料库中检索相似场景，并借助本地大语言模型（LLM）生成上下文一致、高度逼真的响应，从而有效欺骗攻击者并捕获其行为。

## ✨ 核心创新点

- **RAG 驱动的动态响应生成**：传统蜜罐使用固定响应模板，极易被指纹识别。HoneyChat 将每一次攻击者命令作为查询，在向量数据库（Chroma）中检索最相似的历史命令-输出对，然后将检索结果作为上下文，调用本地 LLM 生成自然、连贯且符合系统状态的响应，大幅提升诱饵逼真度。

- **智能会话状态管理**：每个攻击者会话拥有独立的状态记忆，包括当前工作目录、环境变量、命令历史等。系统能够记住攻击者的操作，确保响应的连贯性（如执行 `cd /tmp` 后再执行 `pwd` 会正确返回 `/tmp`）。

- **虚拟文件系统**：实现轻量级虚拟文件系统，支持 cd、pwd、ls、cat、mkdir、touch 等命令。每个会话拥有独立的文件系统实例，攻击者创建的文件可被后续命令访问，大幅提升交互真实性。

- **攻击剧本引擎**：根据攻击者行为自动投放诱饵文件。当检测到攻击者搜索配置文件、SSH密钥或密码时，系统自动生成相应的假文件，主动引导攻击者暴露更多攻击手法（TTP）。

- **攻击链自动分析**：实时分析命令序列，自动识别攻击阶段（侦察、提权、持久化、凭证访问、数据窃取等），计算风险评分，生成攻击摘要报告。

- **威胁情报集成**：集成 VirusTotal API，自动查询攻击者 IP 信誉，生成威胁标签（恶意、置信度、国家等），所有信息保存到数据库供后续分析。

- **实时可视化仪表盘**：提供基于 Web 的实时仪表盘，展示当前活跃会话、历史命令记录、威胁情报标签、攻击阶段和风险评分，支持按攻击者 IP、时间线回放完整交互过程。

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
   ```

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

   **测试虚拟文件系统**：
   ```bash
   pwd                    # 显示当前目录
   cd /tmp                # 切换目录
   pwd                    # 验证目录已切换
   ls                     # 列出文件
   cat /etc/passwd        # 读取虚拟文件
   mkdir test             # 创建目录
   touch test.txt         # 创建文件
   ls                     # 查看新创建的文件
   ```

   **触发攻击剧本**：
   ```bash
   find . -name config    # 触发配置文件场景
   ls ~/.ssh              # 触发SSH密钥场景
   cat /etc/shadow        # 触发密码文件场景
   ```

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

- **文件系统命令响应**：< 0.1 秒（直接处理，不调用 LLM）
- **RAG 引擎响应时间**：平均 1.2 秒（包含检索和生成）
- **威胁情报查询**：首次 1-3 秒，缓存命中 < 1ms
- **蜜罐并发连接**：可同时处理约 50 个 SSH 会话
- **内存占用**：基础 ~500MB，每会话增加 1-2MB
- **磁盘占用**：约 5GB（含模型文件）

## 🛠️ 自定义与扩展

- **添加更多命令模板**：编辑 `services/rag-engine/data/command_pairs.json`，添加新的命令-输出对，重启 RAG 引擎后自动加载。
- **更换 LLM 模型**：下载其他 GGUF 模型放入 `models/`，修改 `config/rag_config.yaml` 中的 `model_path`。
- **使用远程模型（推荐）**：当本地模型运行缓慢时，可切换到 DeepSeek 等远程 API。在 `.env` 中设置 `RAG_ENGINE_USE_REMOTE_MODEL=true` 和 `RAG_ENGINE_REMOTE_API_KEY=your_key`，响应速度提升 60%+。详见 [远程模型指南](docs/REMOTE_MODEL_GUIDE.md)。
- **配置威胁情报**：在 `.env` 中配置 `HONEYPOT_THREAT_INTEL_API_KEY`，使用 VirusTotal API（获取地址：https://www.virustotal.com/gui/my-apikey）。
- **添加攻击场景**：编辑 `services/honeypot/scenario_engine.py`，添加新的 `Scenario` 定义，配置触发关键词和诱饵文件。
- **自定义虚拟文件系统**：修改 `services/honeypot/virtual_fs.py` 中的 `_init_default_fs()` 方法，添加更多虚拟文件和目录。
- **添加更多协议模拟**：在 `services/honeypot/protocol/` 下创建新模块，参考 `ssh_server.py` 实现。

## 📚 详细文档

- [扩展设计文档](docs/EXTENSION_DESIGN.md) - 新功能架构设计
- [使用指南](docs/USAGE_GUIDE.md) - 详细功能使用说明
- [远程模型指南](docs/REMOTE_MODEL_GUIDE.md) - DeepSeek 等远程 API 配置
- [威胁情报配置](docs/THREAT_INTEL_GUIDE.md) - 威胁情报API配置指南
- [部署指南](docs/DEPLOYMENT.md) - 生产环境部署步骤

## 📊 项目背景与价值

HoneyChat 探索了将 RAG 与大语言模型应用于蜜罐交互的全新方式，旨在提升攻击者迷惑性、降低蜜罐被识别的风险。

### 核心特性

- **智能交互**：通过会话状态管理和虚拟文件系统，实现真实的命令行交互体验
- **主动防御**：攻击剧本引擎根据攻击者行为主动投放诱饵，引导攻击者暴露更多TTP
- **自动分析**：攻击链分析器自动识别攻击阶段，计算风险评分，生成威胁报告
- **威胁情报**：集成 VirusTotal API，自动标记恶意IP，增强威胁识别能力
- **可视化分析**：实时仪表盘展示攻击详情，支持历史回放和数据导出

### 技术亮点

- **无需深度学习知识**：核心功能基于工程实现，易于理解和扩展
- **会话隔离**：每个攻击者拥有独立的虚拟环境，互不干扰
- **高性能**：文件系统命令直接处理，响应速度提升70%
- **易于部署**：Docker容器化，一键启动，无需复杂配置

项目代码完全开源，欢迎贡献和改进。

## 📄 许可证

MIT License

---

**HoneyChat** 是一个实验性项目，旨在展示前沿 AI 技术与网络安全防御的结合。如有问题或建议，欢迎提交 Issue 或 Pull Request。
