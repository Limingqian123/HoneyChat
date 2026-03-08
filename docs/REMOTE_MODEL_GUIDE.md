# 远程模型使用指南

## 概述

HoneyChat 现在支持使用远程大语言模型（如 DeepSeek API）作为本地模型的替代方案。当本地模型运行缓慢或资源不足时，可以切换到远程 API 获得更快的响应速度。

## 配置方法

### 1. 获取 API 密钥

访问 [DeepSeek 平台](https://platform.deepseek.com/) 注册并获取 API 密钥。

### 2. 配置环境变量

编辑 `.env` 文件，添加以下配置：

```bash
# 启用远程模型
RAG_ENGINE_USE_REMOTE_MODEL=true

# DeepSeek API 密钥
RAG_ENGINE_REMOTE_API_KEY=your_api_key_here

# API 基础 URL（默认为 DeepSeek）
RAG_ENGINE_REMOTE_API_BASE=https://api.deepseek.com/v1

# 模型名称
RAG_ENGINE_REMOTE_MODEL=deepseek-chat
```

### 3. 重启服务

```bash
docker-compose restart rag-engine
```

## 切换回本地模型

如果需要切换回本地模型，只需修改配置：

```bash
RAG_ENGINE_USE_REMOTE_MODEL=false
```

然后重启服务即可。

## 性能对比

| 模式 | 响应时间 | 资源占用 | 成本 |
|------|---------|---------|------|
| 本地模型 | 1-3秒 | 高（需要 4GB+ 内存） | 免费 |
| 远程模型 | 0.3-0.8秒 | 低（仅网络请求） | 按调用计费 |

## 注意事项

- 远程模型需要稳定的网络连接
- API 调用会产生费用，请注意用量控制
- 向量检索仍在本地进行，只有文本生成使用远程 API
- 确保 API 密钥安全，不要提交到版本控制系统
