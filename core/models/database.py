"""
Database models and schema for Invoice Processing Agent
"""
from sqlalchemy import create_engine, Column, String, Float, Boolean, DateTime, JSON, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()

class Invoice(Base):
    """Main invoice table"""
    __tablename__ = 'invoices'
    
    invoice_id = Column(String, primary_key=True)
    file_path = Column(String, nullable=False)
    file_type = Column(String)
    
    # Extracted data
    vendor_name = Column(String)
    invoice_number = Column(String)
    invoice_date = Column(String)
    total_amount = Column(Float)
    extracted_data = Column(JSON)
    confidence_score = Column(Float)
    
    # Classification
    invoice_type = Column(String)
    
    # Validation
    is_valid = Column(Boolean, default=False)
    validation_errors = Column(JSON)
    
    # Matching
    match_score = Column(Float)
    match_result = Column(String)
    matched_po_number = Column(String)
    
    # Status
    status = Column(String, default='PENDING')  # PENDING, PROCESSING, MATCHED, FAILED, COMPLETED
    approval_status = Column(String)  # AUTO_APPROVED, HUMAN_APPROVED, REJECTED
    erp_transaction_id = Column(String)  # ERP transaction ID after posting
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Checkpoint(Base):
    """Checkpoint model for HITL workflow pause/resume"""
    __tablename__ = 'checkpoints'
    
    hitl_checkpoint_id = Column(String, primary_key=True)
    invoice_id = Column(String, nullable=False)
    state_blob = Column(JSON, nullable=False)
    
    review_url = Column(String)
    paused_reason = Column(String)
    status = Column(String, default='PENDING')  # PENDING, REVIEWED, RESUMED
    
    # Human review fields
    human_decision = Column(String)  # ACCEPT, REJECT
    reviewer_id = Column(String)
    review_notes = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime)
    resumed_at = Column(DateTime)
    
    def __repr__(self):
        return f"<Checkpoint(id={self.hitl_checkpoint_id}, invoice={self.invoice_id}, status={self.status})>"


class AuditLog(Base):
    """Audit log table"""
    __tablename__ = 'audit_logs'
    
    id = Column(String, primary_key=True, default=lambda: f"AUDIT-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}")
    invoice_id = Column(String, nullable=False)
    node_name = Column(String)
    action = Column(String)
    result = Column(String)
    details = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow)


# Database initialization
def init_db():
    """Initialize database and create tables"""
    database_url = os.getenv('DATABASE_URL', 'sqlite:///./invoices.db')
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    return engine


def get_session():
    """Get database session"""
    database_url = os.getenv('DATABASE_URL', 'sqlite:///./invoices.db')
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    return Session()


