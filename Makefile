# Makefile
# HoneyChat 项目构建与运行辅助命令

.PHONY: help build up down logs clean ps prune download-model init-db

help:
	@echo "HoneyChat 管理命令"
	@echo ""
	@echo "Usage:"
	@echo "  make build       # 构建所有 Docker 镜像"
	@echo "  make up          # 启动所有服务 (后台模式)"
	@echo "  make down        # 停止所有服务"
	@echo "  make logs        # 查看所有服务日志 (实时跟踪)"
	@echo "  make ps          # 查看服务状态"
	@echo "  make clean       # 清理未使用的 Docker 资源 (镜像、容器、卷)"
	@echo "  make prune       # 更彻底的清理 (包括构建缓存)"
	@echo "  make download-model  # 下载默认的 LLM 模型文件"
	@echo "  make init-db     # 初始化数据库 (Dashboard)"
	@echo ""

build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

ps:
	docker-compose ps

clean:
	docker system prune -f

prune:
	docker system prune -a -f --volumes

download-model:
	@echo "正在下载默认模型 (llama-2-7b-chat.Q4_K_M.gguf) 到 models/ 目录..."
	mkdir -p models
	cd models && wget -c https://huggingface.co/TheBloke/Llama-2-7B-Chat-GGUF/resolve/main/llama-2-7b-chat.Q4_K_M.gguf
	@echo "模型下载完成"

init-db:
	@echo "初始化 Dashboard 数据库..."
	docker-compose exec dashboard flask shell -c "from app import db; db.create_all()"
	@echo "数据库初始化完成"

# 可选：启动前检查必要的目录
.PHONY: check-dirs
check-dirs:
	mkdir -p data/logs/honeypot data/chroma_db data/dashboard models