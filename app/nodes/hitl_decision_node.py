"""
HITL_DECISION Node - Wait for and process human review decision
"""
from datetime import datetime

from app.nodes.base_node import NonDeterministicNode
from core.models.state import InvoiceState
from core.models.database import get_session, Checkpoint
from core.utils.logging_config import get_logger

logger = get_logger(__name__)


class HitlDecisionNode(NonDeterministicNode):
    """
    HITL_DECISION node: Await human decision via human-review API
    
    Responsibilities:
    - Wait for human decision (ACCEPT or REJECT)
    - Load decision from checkpoint
    - On ACCEPT: return resume_token and next_stage='RECONCILE'
    - On REJECT: finalize with status='MANUAL_HANDOFF'
    """
    
    def __init__(self):
        super().__init__(name="HITL_DECISION")
    
    def execute(self, state: InvoiceState) -> InvoiceState:
        """
        Execute HITL_DECISION logic
        
        Args:
            state: Current workflow state
            
        Returns:
            Updated state with human_decision, reviewer_id, resume_token, next_stage
        """
        logger.info("Processing human review decision")
        
        # Validate required fields
        self.validate_required_fields(state, ['invoice_id', 'hitl_checkpoint_id'])
        
        hitl_checkpoint_id = state['hitl_checkpoint_id']
        
        # Load human decision from checkpoint
        decision_data = self._load_human_decision(hitl_checkpoint_id)
        
        if not decision_data:
            logger.warning(f"No human decision found for checkpoint {hitl_checkpoint_id}")
            state['status'] = 'AWAITING_REVIEW'
            return state
        
        human_decision = decision_data['decision']
        reviewer_id = decision_data['reviewer_id']
        notes = decision_data.get('notes', '')
        
        # Generate resume token
        resume_token = f"RESUME-{hitl_checkpoint_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        # Determine next stage
        if human_decision == 'ACCEPT':
            next_stage = 'RECONCILE'
            status = 'HUMAN_APPROVED'
            logger.info(f"Human ACCEPTED invoice - Reviewer: {reviewer_id}")
        else:  # REJECT
            next_stage = 'COMPLETE'
            status = 'MANUAL_HANDOFF'
            logger.info(f"Human REJECTED invoice - Reviewer: {reviewer_id}")
        
        # Update checkpoint status
        self._update_checkpoint_status(hitl_checkpoint_id, human_decision, reviewer_id)
        
        # Update state
        state['human_decision'] = human_decision
        state['reviewer_id'] = reviewer_id
        state['review_notes'] = notes
        state['resume_token'] = resume_token
        state['next_stage'] = next_stage
        state['status'] = status
        
        logger.info(
            f"Human decision processed - Decision: {human_decision}, "
            f"Next: {next_stage}"
        )
        
        return state
    
    def _load_human_decision(self, hitl_checkpoint_id: str) -> dict:
        """
        Load human decision from checkpoint
        
        Args:
            hitl_checkpoint_id: Checkpoint identifier
            
        Returns:
            Dictionary with decision data or None if not found
        """
        session = get_session()
        try:
            checkpoint = session.query(Checkpoint).filter(
                Checkpoint.hitl_checkpoint_id == hitl_checkpoint_id
            ).first()
            
            if not checkpoint:
                logger.error(f"Checkpoint not found: {hitl_checkpoint_id}")
                return None
            
            if checkpoint.status != 'REVIEWED':
                logger.warning(f"Checkpoint not yet reviewed: {hitl_checkpoint_id}")
                return None
            
            return {
                'decision': checkpoint.human_decision,
                'reviewer_id': checkpoint.reviewer_id,
                'notes': checkpoint.review_notes
            }
            
        except Exception as e:
            logger.error(f"Failed to load human decision: {e}")
            return None
        finally:
            session.close()
    
    def _update_checkpoint_status(
        self,
        hitl_checkpoint_id: str,
        decision: str,
        reviewer_id: str
    ):
        """
        Update checkpoint status after processing decision
        
        Args:
            hitl_checkpoint_id: Checkpoint identifier
            decision: Human decision (ACCEPT/REJECT)
            reviewer_id: Reviewer identifier
        """
        session = get_session()
        try:
            checkpoint = session.query(Checkpoint).filter(
                Checkpoint.hitl_checkpoint_id == hitl_checkpoint_id
            ).first()
            
            if checkpoint:
                checkpoint.status = 'RESUMED'
                checkpoint.resumed_at = datetime.utcnow()
                session.commit()
                logger.info(f"Checkpoint status updated to RESUMED: {hitl_checkpoint_id}")
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update checkpoint status: {e}")
        finally:
            session.close()


# Create node instance
hitl_decision_node = HitlDecisionNode()

