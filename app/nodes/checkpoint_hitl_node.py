"""
CHECKPOINT_HITL Node - Persist state and create review ticket when matching fails
"""
import uuid
from datetime import datetime

from app.nodes.base_node import DeterministicNode
from core.models.state import InvoiceState
from core.models.database import get_session, Checkpoint
from core.utils.error_handler import CheckpointError
from core.utils.logging_config import get_logger
from core.config.config import config

logger = get_logger(__name__)


class CheckpointHitlNode(DeterministicNode):
    """
    CHECKPOINT_HITL node: Persist state and create review ticket when match fails
    
    Trigger Condition: input_state.match_result == 'FAILED'
    
    Responsibilities:
    - Serialize full state to JSON (state_blob)
    - Store in database with unique hitl_checkpoint_id
    - Create review ticket with invoice details
    - Push to human review queue
    - Generate review_url
    - Pause workflow (return interrupt signal)
    """
    
    def __init__(self):
        super().__init__(name="CHECKPOINT_HITL")
        self.review_ui_url = config.REVIEW_UI_URL
    
    def execute(self, state: InvoiceState) -> InvoiceState:
        """
        Execute CHECKPOINT_HITL logic
        
        Args:
            state: Current workflow state
            
        Returns:
            Updated state with hitl_checkpoint_id, review_url, paused_reason
        """
        logger.info("Starting checkpoint creation for human review")
        
        # Validate required fields
        self.validate_required_fields(state, ['invoice_id', 'match_result'])
        
        # Check trigger condition
        match_result = state.get('match_result')
        if match_result != 'FAILED':
            logger.info(f"Checkpoint not needed - match result: {match_result}")
            return state
        
        invoice_id = state['invoice_id']
        
        # Generate checkpoint ID
        hitl_checkpoint_id = f"CHKPT-{invoice_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        # Determine reason for hold
        paused_reason = self._determine_pause_reason(state)
        
        # Generate review URL
        review_url = f"{self.review_ui_url}/{hitl_checkpoint_id}"
        
        # Persist checkpoint to database
        try:
            self._persist_checkpoint(hitl_checkpoint_id, state, paused_reason, review_url)
        except Exception as e:
            logger.error(f"Failed to persist checkpoint: {e}")
            raise CheckpointError(
                f"Failed to create checkpoint: {e}",
                node="CHECKPOINT_HITL",
                recoverable=False
            )
        
        # Update state
        state['hitl_checkpoint_id'] = hitl_checkpoint_id
        state['review_url'] = review_url
        state['paused_reason'] = paused_reason
        state['status'] = 'PENDING_REVIEW'
        
        logger.info(
            f"Checkpoint created - ID: {hitl_checkpoint_id}, "
            f"Reason: {paused_reason}, URL: {review_url}"
        )
        
        # Send email notification to reviewers
        try:
            from integrations.mcp.atlas_mcp_client import get_atlas_client
            
            atlas = get_atlas_client()
            extracted_data = state.get('extracted_data', {})
            
            # Get reviewer emails from config
            reviewer_emails = config.REVIEWER_EMAILS
            
            notification_result = atlas.send_notification(
                notification_type='APPROVAL_NEEDED',
                recipients=reviewer_emails,
                data={
                    'invoice_id': state['invoice_id'],
                    'invoice_number': extracted_data.get('invoice_number', 'N/A'),
                    'vendor_name': extracted_data.get('vendor_name', 'Unknown'),
                    'total_amount': extracted_data.get('total_amount', 0),
                    'status': 'PENDING_REVIEW',
                    'review_url': review_url,
                    'reason': paused_reason
                }
            )
            
            logger.info(f"Review notification sent to {len(reviewer_emails)} reviewers: {notification_result.get('service', 'unknown')}")
            
        except Exception as e:
            logger.warning(f"Failed to send review notification email: {e}")
            # Don't fail the checkpoint creation if email fails
        
        # Note: In LangGraph, this would trigger an interrupt
        # The workflow would pause here until human decision is made
        
        return state
    
    def _determine_pause_reason(self, state: InvoiceState) -> str:
        """
        Determine the reason for pausing the workflow
        
        Args:
            state: Current workflow state
            
        Returns:
            Human-readable reason string
        """
        match_evidence = state.get('match_evidence', {})
        match_score = state.get('match_score', 0)
        
        reasons = []
        
        # Check if no PO found
        matched_pos = state.get('matched_pos', [])
        if not matched_pos:
            vendor_name = state.get('extracted_data', {}).get('vendor_name', 'Unknown')
            reasons.append(f"No matching Purchase Order found for vendor '{vendor_name}'")
            threshold = config.MATCH_THRESHOLD
            reasons.append(f"Match score {match_score:.2f} below threshold {threshold}")
            return "; ".join(reasons)
        
        # Check amount mismatch
        if not match_evidence.get('amount_match', False):
            amount_diff = match_evidence.get('amount_diff', 0)
            amount_diff_pct = match_evidence.get('amount_diff_pct', 0)
            reasons.append(
                f"Amount mismatch: ${abs(amount_diff):.2f} difference ({amount_diff_pct:.1f}%)"
            )
        
        # Check line items mismatch
        if not match_evidence.get('items_match', False):
            items_matched = match_evidence.get('items_matched', 0)
            items_total = match_evidence.get('items_total', 0)
            reasons.append(
                f"Line items mismatch: Only {items_matched}/{items_total} items matched"
            )
        
        # Overall score
        threshold = config.MATCH_THRESHOLD
        reasons.append(f"Match score {match_score:.2f} below threshold {threshold}")
        
        return "; ".join(reasons) if reasons else "Manual review required"
    
    def _persist_checkpoint(
        self,
        hitl_checkpoint_id: str,
        state: InvoiceState,
        paused_reason: str,
        review_url: str
    ):
        """
        Persist checkpoint to database
        
        Args:
            hitl_checkpoint_id: Unique checkpoint identifier
            state: Current workflow state
            paused_reason: Reason for pause
            review_url: URL for human review
        """
        import json
        
        session = get_session()
        try:
            # Serialize state
            state_blob = json.dumps(state, default=str)
            
            # Create checkpoint record
            checkpoint = Checkpoint(
                hitl_checkpoint_id=hitl_checkpoint_id,
                invoice_id=state['invoice_id'],
                state_blob=state_blob,
                review_url=review_url,
                paused_reason=paused_reason,
                status='PENDING'
            )
            
            session.add(checkpoint)
            session.commit()
            
            logger.info(f"Checkpoint persisted to database: {hitl_checkpoint_id}")
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to persist checkpoint: {e}")
            raise
        finally:
            session.close()


# Create node instance
checkpoint_hitl_node = CheckpointHitlNode()

