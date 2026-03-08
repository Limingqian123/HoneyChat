# HoneyChat 扩展方案设计文档

## 🎯 扩展目标

将 HoneyChat 从简单的命令响应蜜罐升级为具有**会话记忆**和**虚拟环境**的智能交互式蜜罐。

## 🏗️ 核心创新点

### 1. 会话状态管理 (SessionManager)
**问题**：现有系统每次命令处理都是独立的，无法记住上下文
**解决**：为每个 session 维护状态字典，包括：
- 当前工作目录 (cwd)
- 环境变量 (env)
- 命令历史 (history)
- 虚拟文件系统状态

### 2. 虚拟文件系统 (VirtualFileSystem)
**问题**：ls、cat、cd 等命令响应不真实，攻击者容易识破
**解决**：用字典模拟文件系统结构，支持：
- 目录导航 (cd, pwd)
- 文件列表 (ls)
- 文件读取 (cat)
- 文件创建 (touch, echo >)
- 目录创建 (mkdir)

### 3. 攻击剧本引擎 (ScenarioEngine)
**问题**：被动防御，无法主动引导攻击者
**解决**：预设攻击场景，主动投放诱饵：
- 假的密码文件 (/etc/shadow.bak)
- 假的配置文件 (config.php 含数据库密码)
- 假的私钥文件 (.ssh/id_rsa)
- 根据攻击者行为动态调整

### 4. 攻击链分析 (AttackChainAnalyzer)
**问题**：无法理解攻击者的完整攻击流程
**解决**：分析命令序列，识别攻击阶段：
- 侦察 (whoami, uname, ifconfig)
- 权限提升 (sudo, su)
- 持久化 (crontab, systemctl)
- 数据窃取 (find, grep, tar)

## 📐 架构设计

```
services/honeypot/
├── handler.py (修改)
├── session_manager.py (新增)
├── virtual_fs.py (新增)
├── scenario_engine.py (新增)
└── attack_analyzer.py (新增)
```

## 🔄 工作流程

```
攻击者输入命令
    ↓
SessionManager 加载会话状态
    ↓
VirtualFileSystem 处理文件系统命令 (cd/ls/cat等)
    ↓
如果是文件系统命令 → 直接返回虚拟结果
如果不是 → 调用 RAG 引擎生成响应
    ↓
ScenarioEngine 检查是否需要投放诱饵
    ↓
SessionManager 更新会话状态
    ↓
AttackChainAnalyzer 分析攻击阶段
    ↓
返回响应给攻击者
```

## 📊 预期效果

### 改进前
```
攻击者: cd /tmp
系统: (RAG随机生成)
攻击者: pwd
系统: /home/user  ← 不一致！
```

### 改进后
```
攻击者: cd /tmp
系统: (虚拟文件系统处理)
攻击者: pwd
系统: /tmp  ← 一致！
攻击者: ls
系统: file1.txt  file2.sh  ← 虚拟文件
攻击者: cat file1.txt
系统: [诱饵内容：假密码]
```

## 🚀 实施步骤

1. **第一阶段**：实现 SessionManager + VirtualFileSystem
   - 时间：2-3天
   - 效果：命令响应连贯性提升 80%

2. **第二阶段**：实现 ScenarioEngine
   - 时间：2-3天
   - 效果：主动诱导攻击者，捕获更多 TTP

3. **第三阶段**：实现 AttackChainAnalyzer + 可视化
   - 时间：3-4天
   - 效果：自动生成攻击报告

## 💻 技术栈

- Python 3.9+
- 无需额外依赖（使用标准库）
- 兼容现有 Docker 架构

## 📈 性能影响

- 内存增加：每个 session 约 1-2MB
- 响应时间：减少 0.3-0.5秒（文件系统命令不调用 LLM）
- 存储增加：每个 session 约 10-50KB

## 🎓 学习成本

- ✅ 无需深度学习知识
- ✅ 基于 Python 字典和类
- ✅ 代码简洁易懂
- ✅ 可逐步扩展
