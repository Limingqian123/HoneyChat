# services/dashboard/models.py
"""
Dashboard 服务数据库模型。

定义事件表，存储蜜罐捕获的攻击交互记录。
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index
from sqlalchemy.types import JSON

db = SQLAlchemy()


class Event(db.Model):
    """攻击事件模型"""

    __tablename__ = 'events'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(64), nullable=False, index=True)
    command = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=True)
    client_ip = db.Column(db.String(45), nullable=True, index=True)  # IPv6 最长45
    protocol = db.Column(db.String(10), nullable=False, default='ssh')
    threat_tags = db.Column(JSON, nullable=True, default=list)
    error = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.Float, nullable=False)  # Unix timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # 新增字段
    attack_phase = db.Column(db.String(50), nullable=True)  # 攻击阶段
    risk_score = db.Column(db.Integer, nullable=True, default=0)  # 风险评分

    # 复合索引
    __table_args__ = (
        Index('ix_events_client_ip_timestamp', 'client_ip', 'timestamp'),
        Index('ix_events_session_id_timestamp', 'session_id', 'timestamp'),
    )

    def __repr__(self):
        return f'<Event {self.id} {self.session_id} {self.command[:20]}>'

    def to_dict(self):
        """转换为字典，用于 API 返回"""
        return {
            'id': self.id,
            'session_id': self.session_id,
            'command': self.command,
            'response': self.response,
            'client_ip': self.client_ip,
            'protocol': self.protocol,
            'threat_tags': self.threat_tags or [],
            'error': self.error,
            'timestamp': self.timestamp,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'attack_phase': self.attack_phase,
            'risk_score': self.risk_score,
        }