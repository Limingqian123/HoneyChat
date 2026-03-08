# 🛡️ 威胁情报功能使用指南

## ✅ 功能已修复

威胁情报API现在已经完全集成到主流程中！

## 🔧 配置步骤

### 1. 获取 VirusTotal API Key

1. 访问 https://www.virustotal.com/gui/my-apikey
2. 注册或登录账号
3. 复制你的 API Key

### 2. 配置环境变量

编辑 `.env` 文件：

```bash
# 启用威胁情报
HONEYPOT_ENABLE_THREAT_INTEL=true

# 配置 VirusTotal API Key
HONEYPOT_THREAT_INTEL_API_KEY=your_actual_api_key_here

# 缓存时间（秒）
HONEYPOT_THREAT_INTEL_CACHE_TTL=3600
```

### 3. 重启服务

```bash
docker-compose restart honeypot
```

## 📊 工作原理

### 自动查询流程

1. **首次命令时查询**：当攻击者首次连接并执行命令时，系统自动查询其IP
2. **结果缓存**：查询结果缓存1小时（可配置）
3. **标签生成**：根据威胁情报生成标签
4. **记录到数据库**：标签保存到事件记录中

### 生成的标签

| 标签 | 含义 |
|------|------|
| `malicious` | IP被标记为恶意 |
| `high_confidence` | 置信度 ≥ 80% |
| `medium_confidence` | 置信度 50-79% |
| `low_confidence` | 置信度 < 50% |
| `country_cn` | 来自中国（示例） |
| `reports_5` | 有5个恶意报告 |

## 🧪 测试验证

### 查看日志

```bash
docker-compose logs -f honeypot | grep "threat"
```

**成功示例**：
```
Malicious IP detected ip=1.2.3.4 confidence=85 tags=['malicious', 'high_confidence']
```

### 查看仪表盘

访问 http://localhost:5000，查看事件的 `threat_tags` 字段。

## ⚙️ 配置选项

### 禁用威胁情报

```bash
HONEYPOT_ENABLE_THREAT_INTEL=false
```

### 调整缓存时间

```bash
# 缓存30分钟
HONEYPOT_THREAT_INTEL_CACHE_TTL=1800

# 缓存2小时
HONEYPOT_THREAT_INTEL_CACHE_TTL=7200
```

## 🔍 故障排查

### 问题1: API Key无效

**日志**：
```
VirusTotal API error status=401
```

**解决**：检查API Key是否正确配置

### 问题2: 速率限制

**日志**：
```
Rate limited by VirusTotal
```

**解决**：
- 免费账号：4次/分钟
- 升级到付费账号或增加缓存时间

### 问题3: 查询超时

**日志**：
```
Timeout querying VirusTotal
```

**解决**：网络问题，系统会自动重试

## 📈 性能影响

- **首次查询**：增加 1-3 秒延迟
- **缓存命中**：几乎无延迟（< 1ms）
- **内存占用**：每个IP约 1KB

## 🎯 最佳实践

1. **启用缓存**：使用默认的3600秒缓存
2. **监控日志**：定期检查恶意IP检测
3. **定期更新**：VirusTotal数据库持续更新
