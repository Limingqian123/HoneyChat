# services/dashboard/app.py
"""
HoneyChat Dashboard 主应用。

提供 Web 界面实时展示攻击事件，并通过 API 接收蜜罐推送的事件。
"""

import os
import time
from datetime import datetime
from typing import List, Optional

from flask import Flask, render_template, request, jsonify, abort
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from sqlalchemy import desc
import structlog

from config import settings, setup_logging
from models import db, Event

# 配置结构化日志
setup_logging()
logger = structlog.get_logger(__name__)

# 创建 Flask 应用
app = Flask(__name__)

# 加载配置
app.config['SECRET_KEY'] = settings.secret_key
app.config['SQLALCHEMY_DATABASE_URI'] = settings.database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': settings.database_pool_size,
    'max_overflow': settings.database_max_overflow,
}

# 初始化数据库
db.init_app(app)

# 初始化 CORS
cors_origins = settings.get_cors_origins_list()
CORS(app, origins=cors_origins)

# 初始化 SocketIO (使用 eventlet 作为异步模式)
socketio = SocketIO(app, cors_allowed_origins=cors_origins, async_mode='eventlet')

# 创建数据库表（如果不存在）
with app.app_context():
    db.create_all()
    logger.info("Database tables ensured")


# ---------- 路由 ----------
@app.route('/')
def index():
    """渲染仪表盘主页"""
    return render_template('index.html')


@app.route('/health')
def health():
    """健康检查端点"""
    # 简单检查数据库连接
    try:
        db.session.execute('SELECT 1').scalar()
        db_status = 'ok'
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        db_status = 'error'

    status = {
        'status': 'healthy' if db_status == 'ok' else 'degraded',
        'timestamp': time.time(),
        'database': db_status,
    }
    return jsonify(status)


@app.route('/api/events', methods=['POST'])
def receive_event():
    """
    接收蜜罐推送的事件并存储。
    期望 JSON 格式:
    {
        "session_id": "...",
        "command": "...",
        "response": "...",
        "client_ip": "...",
        "protocol": "ssh|http",
        "threat_tags": ["tag1", "tag2"],
        "error": "...",
        "timestamp": 1234567890.123
    }
    """
    data = request.get_json()
    if not data:
        logger.warning("Received empty JSON")
        abort(400, description="Empty JSON")

    # 验证必要字段
    required_fields = ['session_id', 'command', 'timestamp']
    for field in required_fields:
        if field not in data:
            logger.warning("Missing required field", field=field, data=data)
            abort(400, description=f"Missing required field: {field}")

    # 创建事件记录
    try:
        event = Event(
            session_id=data['session_id'],
            command=data['command'],
            response=data.get('response', ''),
            client_ip=data.get('client_ip'),
            protocol=data.get('protocol', 'ssh'),
            threat_tags=data.get('threat_tags', []),
            error=data.get('error'),
            timestamp=data['timestamp'],
            attack_phase=data.get('attack_phase'),
            risk_score=data.get('risk_score', 0),
        )
        db.session.add(event)
        db.session.commit()

        logger.info("Event stored", event_id=event.id, session_id=event.session_id)

        # 通过 SocketIO 广播新事件
        socketio.emit('new_event', event.to_dict())

        return jsonify({'status': 'ok', 'id': event.id}), 201

    except Exception as e:
        db.session.rollback()
        logger.exception("Failed to store event", error=str(e))
        abort(500, description="Internal server error")


@app.route('/api/events', methods=['GET'])
def list_events():
    """
    查询事件列表。
    支持查询参数:
        session_id: 过滤会话ID
        client_ip: 过滤客户端IP
        limit: 返回条数 (默认 100, 最大 1000)
        offset: 分页偏移
    """
    session_id = request.args.get('session_id')
    client_ip = request.args.get('client_ip')
    try:
        limit = int(request.args.get('limit', 100))
        if limit > 1000:
            limit = 1000
    except ValueError:
        limit = 100

    try:
        offset = int(request.args.get('offset', 0))
    except ValueError:
        offset = 0

    query = Event.query.order_by(desc(Event.timestamp))

    if session_id:
        query = query.filter(Event.session_id == session_id)
    if client_ip:
        query = query.filter(Event.client_ip == client_ip)

    total = query.count()
    events = query.limit(limit).offset(offset).all()

    return jsonify({
        'total': total,
        'offset': offset,
        'limit': limit,
        'events': [e.to_dict() for e in events]
    })


@app.route('/api/events/<int:event_id>', methods=['GET'])
def get_event(event_id):
    """获取单个事件详情"""
    event = Event.query.get(event_id)
    if not event:
        abort(404, description="Event not found")
    return jsonify(event.to_dict())


@app.route('/api/stats', methods=['GET'])
def stats():
    """获取简单统计信息"""
    try:
        total_events = Event.query.count()
        unique_ips = db.session.query(Event.client_ip).distinct().count()
        last_event = Event.query.order_by(desc(Event.timestamp)).first()
        last_time = last_event.timestamp if last_event else None

        return jsonify({
            'total_events': total_events,
            'unique_ips': unique_ips,
            'last_event_time': last_time,
        })
    except Exception as e:
        logger.exception("Stats error", error=str(e))
        abort(500, description="Internal server error")


# ---------- SocketIO 事件 ----------
@socketio.on('connect')
def handle_connect():
    """客户端连接时记录"""
    logger.info("SocketIO client connected", sid=request.sid)


@socketio.on('disconnect')
def handle_disconnect():
    """客户端断开时记录"""
    logger.info("SocketIO client disconnected", sid=request.sid)


# ---------- 错误处理 ----------
@app.errorhandler(400)
def bad_request(e):
    return jsonify({'error': e.description}), 400


@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Internal server error'}), 500


# ---------- 启动入口 ----------
if __name__ == '__main__':
    # 开发环境直接运行（不通过 gunicorn）
    socketio.run(app, host=settings.host, port=settings.port, debug=settings.debug)