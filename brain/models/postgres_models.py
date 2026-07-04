import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from brain.database import Base

def get_utc_now():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=get_utc_now)


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    api_key_hash = Column(String, nullable=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    status = Column(String, default="active")
    
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    sessions = relationship("Session", back_populates="project", cascade="all, delete-orphan")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(String, default="IN_PROGRESS")
    active_node = Column(String, nullable=True)
    progress_percentage = Column(Float, default=0.0)
    dag = Column(JSON, nullable=True)
    git_commit_hash = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    project = relationship("Project", back_populates="sessions")
    artifacts = relationship("Artifact", back_populates="session", cascade="all, delete-orphan")
    execution_logs = relationship("ExecutionLog", back_populates="session", cascade="all, delete-orphan")
    evaluations = relationship("Evaluation", back_populates="session", cascade="all, delete-orphan")
    predictions = relationship("Prediction", back_populates="session", cascade="all, delete-orphan")
    optimizations = relationship("Optimization", back_populates="session", cascade="all, delete-orphan")
    learning_reports = relationship("LearningReport", back_populates="session", cascade="all, delete-orphan")
    decisions = relationship("Decision", back_populates="session", cascade="all, delete-orphan")


class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    artifact_type = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    version = Column(Integer, default=1)
    checksum = Column(String, nullable=False)
    generated_by = Column(String, nullable=False)
    depends_on = Column(JSON, default=list)
    used_by = Column(JSON, default=list)
    
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    session = relationship("Session", back_populates="artifacts")


class ExecutionLog(Base):
    __tablename__ = "execution_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime, default=get_utc_now)
    agent = Column(String, nullable=False)
    action = Column(String, nullable=False)
    details = Column(JSON, default=dict)
    
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    session = relationship("Session", back_populates="execution_logs")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    composite_score = Column(Float, nullable=False)
    passed = Column(Boolean, default=True)
    metrics = Column(JSON, default=dict)
    checks = Column(JSON, default=list)
    evaluated_at = Column(DateTime, default=get_utc_now)
    
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    session = relationship("Session", back_populates="evaluations")


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    target_node = Column(String, nullable=False)
    predicted_failures = Column(JSON, default=list)
    confidence = Column(Float, nullable=False)
    
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    session = relationship("Session", back_populates="predictions")


class Optimization(Base):
    __tablename__ = "optimizations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    target_node = Column(String, nullable=False)
    recommendations = Column(JSON, default=list)
    impact_score = Column(Float, nullable=False)
    
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    session = relationship("Session", back_populates="optimizations")


class LearningReport(Base):
    __tablename__ = "learning_reports"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    patterns_extracted = Column(JSON, default=dict)
    recommendations = Column(JSON, default=list)
    
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    session = relationship("Session", back_populates="learning_reports")


class Decision(Base):
    __tablename__ = "decisions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    agent = Column(String, nullable=False)
    node = Column(String, nullable=False)
    title = Column(String, nullable=False)
    rationale = Column(String, nullable=False)
    confidence_score = Column(Float, default=1.0)
    alternatives_considered = Column(JSON, default=list)
    artifacts_produced = Column(JSON, default=list)
    timestamp = Column(DateTime, default=get_utc_now)
    
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    session = relationship("Session", back_populates="decisions")


class AgentRegistry(Base):
    __tablename__ = "agent_registries"

    name = Column(String, primary_key=True)
    description = Column(String, nullable=False)
    status = Column(String, default="active")
    system_prompt = Column(String, nullable=False)
    capabilities = Column(JSON, default=dict)
    inputs = Column(JSON, default=list)
    outputs = Column(JSON, default=list)
    skills = Column(JSON, default=list)
    mcp_servers = Column(JSON, default=list)
    registered_at = Column(DateTime, default=get_utc_now)
    
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)
