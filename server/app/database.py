"""Database models and session management"""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import (
    Column, String, Numeric, Date, DateTime, ForeignKey, Index, Text,
    create_engine, Boolean, Integer, JSON
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from app.config import settings
from app.logger import create_logger

logger = create_logger("database")

Base = declarative_base()

# Test user configuration
TEST_USER_EMAIL = "test@local.dev"
TEST_USER_NAME = "Test User"


def _utc_now():
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)

# Use String for SQLite, UUID for PostgreSQL
def UUIDColumn():
    """Return appropriate UUID column type based on database"""
    if settings.database_url.startswith("sqlite"):
        return Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    else:
        return Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)

def UUIDForeignKey(foreign_key):
    """Return appropriate UUID foreign key column type based on database"""
    if settings.database_url.startswith("sqlite"):
        return Column(String(36), ForeignKey(foreign_key), nullable=False, index=True)
    else:
        return Column(PostgresUUID(as_uuid=True), ForeignKey(foreign_key), nullable=False, index=True)


class User(Base):
    """User model"""
    __tablename__ = "users"

    id = UUIDColumn()
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255))
    password_hash = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=_utc_now, nullable=False)

    # Relationships
    categorization_preferences = relationship("CategorizationPreference", back_populates="user", cascade="all, delete-orphan")
    budgets = relationship("Budget", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    rule_analysis_runs = relationship("RuleAnalysisRun", back_populates="user", cascade="all, delete-orphan")
    rule_analysis_findings = relationship("RuleAnalysisFinding", back_populates="user", cascade="all, delete-orphan")
    custom_categories = relationship("CustomCategory", back_populates="user", cascade="all, delete-orphan")


class CategorizationPreference(Base):
    """Unified preference model for categorization rules and parsing instructions"""
    __tablename__ = "categorization_preferences"

    id = UUIDColumn()
    user_id = UUIDForeignKey("users.id")
    bank_name = Column(String(100), nullable=True, index=True)  # NULL = global rule (for categorization)
    name = Column(String(200), nullable=False)  # Human-readable rule/instruction name
    rule = Column(JSON, nullable=False)  # Structured rule or parsing instruction definition
    priority = Column(Integer, default=0, nullable=False)  # Higher = higher priority
    enabled = Column(Boolean, default=True, nullable=False)
    preference_type = Column(String(20), nullable=False, default="categorization")  # "categorization" or "parsing"
    created_at = Column(DateTime, default=_utc_now, nullable=False)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now, nullable=False)

    # Relationships
    user = relationship("User", back_populates="categorization_preferences")

    __table_args__ = (
        Index("idx_cat_pref_user_bank", "user_id", "bank_name"),
        Index("idx_cat_pref_user_priority", "user_id", "priority"),
        Index("idx_cat_pref_user_type", "user_id", "preference_type"),
    )


class Budget(Base):
    """Budget model - stores user-defined budget targets per category/month
    
    NOTE: The unique index on (user_id, category, month_year) does NOT prevent
    multiple rows with NULL month_year due to SQL NULL semantics (NULL != NULL).
    The save_budget handler must explicitly check for existing NULL values
    before inserting new default budgets.
    """
    __tablename__ = "budgets"

    id = UUIDColumn()
    user_id = UUIDForeignKey("users.id")
    category = Column(String(100), nullable=False, index=True)
    month_year = Column(String(7), nullable=True, index=True)  # YYYY-MM format, NULL = default budget
    amount = Column(Numeric(12, 2), nullable=False)  # Budget target amount (positive for expenses)
    currency = Column(String(3), nullable=False, default="USD")
    created_at = Column(DateTime, default=_utc_now, nullable=False)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now, nullable=False)

    # Relationships
    user = relationship("User", back_populates="budgets")

    __table_args__ = (
        # NOTE: This unique index does NOT prevent multiple NULLs for month_year.
        # Application code in save_budget.py handles this explicitly.
        Index("idx_budget_user_category_month", "user_id", "category", "month_year", unique=True),
        Index("idx_budget_user_category", "user_id", "category"),
    )




class Transaction(Base):
    """Transaction model - stores individual transaction records"""
    __tablename__ = "transactions"

    id = UUIDColumn()
    user_id = UUIDForeignKey("users.id")
    date = Column(Date, nullable=False, index=True)
    description = Column(String(500), nullable=False)
    merchant = Column(String(200), nullable=True, index=True)
    amount = Column(Numeric(12, 2), nullable=False)  # Negative for expenses, positive for income
    currency = Column(String(3), nullable=False)
    category = Column(String(100), nullable=False, index=True)
    original_amount = Column(Numeric(12, 2), nullable=True)  # Pre-conversion amount (NULL if no conversion)
    original_currency = Column(String(3), nullable=True)  # Statement's native currency when != functional
    exchange_rate = Column(Numeric(18, 8), nullable=True)  # Rate applied: functional_ccy / original_ccy
    category_source = Column(String(20), nullable=True, index=True)  # 'rule', 'ai', 'manual'
    bank_name = Column(String(100), nullable=False, index=True)
    profile = Column(String(50), nullable=True, index=True)  # Household profile (e.g., "Me", "Partner", "Joint")
    review_status = Column(String(20), nullable=True, index=True)  # NULL, 'confirmed', 'conflict'
    review_category = Column(String(100), nullable=True)  # Reviewer's alternative suggestion (conflict only)
    review_reason = Column(Text, nullable=True)  # Reviewer's explanation for flagging
    created_at = Column(DateTime, default=_utc_now, nullable=False)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now, nullable=False)

    # Relationships
    user = relationship("User", back_populates="transactions")

    __table_args__ = (
        Index("idx_transactions_user_date", "user_id", "date"),
        Index("idx_transactions_user_category", "user_id", "category"),
        Index("idx_transactions_user_merchant", "user_id", "merchant"),
        Index("idx_transactions_user_bank_date", "user_id", "bank_name", "date"),
        Index("idx_transactions_review_status", "user_id", "review_status"),
    )


class RuleAnalysisRun(Base):
    """Rule analysis job run metadata."""

    __tablename__ = "rule_analysis_runs"

    id = UUIDColumn()
    user_id = UUIDForeignKey("users.id")
    status = Column(String(20), nullable=False, default="queued", index=True)
    scope_since = Column(Date, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    summary_json = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utc_now, nullable=False)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now, nullable=False)

    user = relationship("User", back_populates="rule_analysis_runs")
    findings = relationship("RuleAnalysisFinding", back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_rule_analysis_runs_user_created", "user_id", "created_at"),
        Index("idx_rule_analysis_runs_user_status_created", "user_id", "status", "created_at"),
    )


class RuleAnalysisFinding(Base):
    """Actionable finding emitted by a rule analysis run."""

    __tablename__ = "rule_analysis_findings"

    id = UUIDColumn()
    run_id = UUIDForeignKey("rule_analysis_runs.id")
    user_id = UUIDForeignKey("users.id")
    finding_type = Column(String(30), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="open", index=True)
    confidence = Column(Numeric(4, 3), nullable=False, default=0.0)
    bank_name = Column(String(100), nullable=True, index=True)
    payload_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=_utc_now, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now, nullable=False)

    run = relationship("RuleAnalysisRun", back_populates="findings")
    user = relationship("User", back_populates="rule_analysis_findings")

    __table_args__ = (
        Index("idx_rule_analysis_findings_run_status", "run_id", "status"),
        Index("idx_rule_analysis_findings_user_status_created", "user_id", "status", "created_at"),
    )


class CustomCategory(Base):
    """User-defined custom spending categories."""

    __tablename__ = "custom_categories"

    id = UUIDColumn()
    user_id = UUIDForeignKey("users.id")
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=_utc_now, nullable=False)

    user = relationship("User", back_populates="custom_categories")

    __table_args__ = (
        Index("idx_custom_categories_user", "user_id"),
        Index("idx_custom_categories_user_name", "user_id", "name", unique=True),
    )


# Database engine and session
connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)


def get_or_create_test_user() -> str:
    """
    Get or create a test user for local development.
    
    Returns:
        str: User ID (UUID as string for SQLite compatibility)
    """
    db = SessionLocal()
    try:
        test_user = db.query(User).filter(User.email == TEST_USER_EMAIL).first()
        
        if not test_user:
            test_user = User(
                email=TEST_USER_EMAIL,
                name=TEST_USER_NAME
            )
            db.add(test_user)
            db.commit()
            db.refresh(test_user)
        
        return str(test_user.id)
    finally:
        db.close()


def resolve_user_id(user_id: str | None = None, require_auth: bool = False) -> str:
    """
    Resolve and validate a user_id.
    
    For multi-user support: if require_auth is True, user_id must be provided and valid.
    Otherwise, falls back to test user for development.
    
    Args:
        user_id: Optional user ID string to validate
        require_auth: If True, user_id is required and must exist (no test user fallback)
        
    Returns:
        str: Valid user ID
        
    Raises:
        ValueError: If require_auth is True and user_id is None or invalid
    """
    # If no user_id provided
    if not user_id:
        if require_auth:
            raise ValueError("User ID is required but not provided")
        return get_or_create_test_user()
    
    user_id_str = str(user_id)
    
    # Validate that this user_id exists in the database
    db = SessionLocal()
    try:
        existing_user = db.query(User).filter(User.id == user_id_str).first()
        if existing_user:
            return user_id_str
        else:
            # User doesn't exist
            if require_auth:
                raise ValueError(f"User ID {user_id_str} does not exist")
            # Fall back to test user for development
            logger.warn("User ID not found, falling back to test user", {"user_id": user_id_str})
            return get_or_create_test_user()
    finally:
        db.close()
