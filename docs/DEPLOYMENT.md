# 🚀 快速部署指南

## 📋 部署前准备

### 1. 检查文件完整性
确保以下文件存在：
```bash
services/honeypot/
├── session_manager.py      ✓ 新增
├── virtual_fs.py           ✓ 新增
├── scenario_engine.py      ✓ 新增
├── attack_analyzer.py      ✓ 新增
└── handler.py              ✓ 已修改

services/dashboard/
├── models.py               ✓ 已修改
└── app.py                  ✓ 已修改
```

## 🔧 部署步骤

### 步骤1: 备份数据（重要！）
```bash
# 备份现有数据库
cp data/dashboard/events.db data/dashboard/events.db.backup.$(date +%Y%m%d)
```

### 步骤2: 停止服务
```bash
docker-compose down
```

### 步骤3: 处理数据库迁移

**选项A: 开发环境（推荐）**
```bash
# 删除旧数据库，让系统自动创建新表结构
rm data/dashboard/events.db
```

**选项B: 生产环境（保留数据）**
```bash
# 手动添加新字段
sqlite3 data/dashboard/events.db << EOF
ALTER TABLE events ADD COLUMN attack_phase VARCHAR(50);
ALTER TABLE events ADD COLUMN risk_score INTEGER DEFAULT 0;
EOF
```

### 步骤4: 重新构建并启动
```bash
# 重新构建honeypot服务
docker-compose build honeypot

# 重新构建dashboard服务
docker-compose build dashboard

# 启动所有服务
docker-compose up -d
```

### 步骤5: 检查服务状态
```bash
# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f honeypot
docker-compose logs -f dashboard
```

## ✅ 功能验证

### 测试1: 基础连接
```bash
ssh root@localhost -p 2222
# 任意密码登录
```

### 测试2: 虚拟文件系统
```bash
pwd                    # 应显示 /home/user
cd /tmp
pwd                    # 应显示 /tmp
ls
cat /etc/passwd
```

### 测试3: 攻击剧本触发
```bash
find . -name config
ls ~/.ssh
cat /etc/shadow
```

### 测试4: 查看仪表盘
```bash
# 浏览器访问
http://localhost:5000

# 检查新字段是否显示
# - attack_phase
# - risk_score
```

## 🐛 故障排查

### 问题1: 导入错误
```
ModuleNotFoundError: No module named 'session_manager'
```
**解决**: 检查文件是否在正确位置，重新构建镜像

### 问题2: 数据库错误
```
no such column: events.attack_phase
```
**解决**: 执行数据库迁移（步骤3）

### 问题3: 服务无法启动
```bash
# 查看详细日志
docker-compose logs honeypot
docker-compose logs dashboard

# 检查端口占用
netstat -an | grep 2222
netstat -an | grep 5000
```

## 📊 验证成功标志

- ✅ SSH可以连接（端口2222）
- ✅ pwd/cd命令响应一致
- ✅ ls显示虚拟文件
- ✅ 仪表盘显示attack_phase和risk_score
- ✅ 日志中看到"Scenario triggered"消息

## 🎉 部署完成

如果所有测试通过，恭喜你！HoneyChat扩展功能已成功部署。

现在你的蜜罐具备：
- ✨ 会话状态记忆
- ✨ 真实的文件系统交互
- ✨ 智能诱饵投放
- ✨ 自动攻击分析
