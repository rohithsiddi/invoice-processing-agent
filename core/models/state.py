"""
State schema for Invoice Processing workflow
"""
from typing import TypedDict, List, Dict, Optional
from datetime import datetime


class InvoiceState(TypedDict, total=False):
    """
    Complete state schema for the invoice processing workflow.
    Each node updates specific fields in this state.
    """
    
    # INGEST node outputs
    invoice_id: str
    file_path: str
    file_type: str
    
    # EXTRACT node outputs
    extracted_data: Dict[str, any]
    confidence_score: float
    
    # CLASSIFY node outputs
    invoice_type: str
    
    # ENRICH node outputs
    vendor_info: Dict[str, any]
    
    # VALIDATE node outputs
    validation_errors: List[str]
    is_valid: bool
    
    # RETRIEVE node outputs
    matched_pos: List[Dict]
    matched_grns: List[Dict]
    history: List[Dict]
    
    # MATCH_TWO_WAY node outputs
    match_score: float
    match_result: str  # "MATCHED" or "FAILED"
    tolerance_pct: float
    match_evidence: Dict[str, any]
    
    # HITL (Human-in-the-Loop) fields
    hitl_checkpoint_id: Optional[str]
    review_url: Optional[str]
    paused_reason: Optional[str]
    
    # HITL_DECISION node outputs
    human_decision: Optional[str]  # "ACCEPT" or "REJECT"
    reviewer_id: Optional[str]
    resume_token: Optional[str]
    next_stage: Optional[str]
    
    # RECONCILE node outputs
    accounting_entries: List[Dict]
    reconciliation_report: Dict[str, any]
    
    # APPROVE node outputs
    approval_status: str
    approver_id: Optional[str]
    
    # POSTING node outputs
    posted: bool
    erp_txn_id: Optional[str]
    scheduled_payment_id: Optional[str]
    
    # NOTIFY node outputs
    notify_status: Dict[str, str]
    notified_parties: List[str]
    
    # COMPLETE node outputs
    final_payload: Dict[str, any]
    audit_log: List[Dict]
    status: str
    
    # Metadata
    created_at: Optional[str]
    updated_at: Optional[str]
