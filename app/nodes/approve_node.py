"""
APPROVE Node - Apply approval policies based on amount thresholds
"""
from typing import Dict, Any
from datetime import datetime

from app.nodes.base_node import DeterministicNode
from core.models.state import InvoiceState
from core.config.config import config
from core.utils.logging_config import get_logger

logger = get_logger(__name__)


class ApproveNode(DeterministicNode):
    """
    APPROVE node: Apply approval policies based on invoice amount
    
    Responsibilities:
    - Check if invoice amount exceeds auto-approval threshold
    - If amount <= threshold: auto-approve
    - If amount > threshold: require manual approval
    - Record approval decision and approver
    """
    
    def __init__(self):
        super().__init__(name="APPROVE")
        self.auto_approve_threshold = config.AUTO_APPROVE_THRESHOLD
    
    def execute(self, state: InvoiceState) -> InvoiceState:
        """
        Execute APPROVE logic
        
        Args:
            state: Current workflow state
            
        Returns:
            Updated state with approval_status, approver, approval_reason
        """
        logger.info("Starting approval process")
        
        # Validate required fields
        self.validate_required_fields(state, ['invoice_id', 'extracted_data'])
        
        extracted_data = state['extracted_data']
        total_amount = extracted_data.get('total_amount', 0)
        invoice_id = state['invoice_id']
        
        # Determine approval based on policies
        approval_result = self._apply_approval_policies(state, total_amount)
        
        # Update state
        state['approval_status'] = approval_result['status']
        state['approver'] = approval_result['approver']
        state['approval_reason'] = approval_result['reason']
        state['approval_timestamp'] = datetime.utcnow().isoformat()
        state['status'] = approval_result['workflow_status']
        
        logger.info(
            f"Approval complete - Status: {approval_result['status']}, "
            f"Amount: ${total_amount:,.2f}, Approver: {approval_result['approver']}"
        )
        
        return state
    
    def _apply_approval_policies(
        self,
        state: InvoiceState,
        amount: float
    ) -> Dict[str, Any]:
        """
        Apply approval policies based on vendor and validation status
        
        Args:
            state: Current workflow state
            amount: Invoice total amount
            
        Returns:
            Dictionary with approval decision
        """
        # Policy 1: Check if human already approved (from HITL)
        human_decision = state.get('human_decision')
        if human_decision == 'ACCEPT':
            reviewer_id = state.get('reviewer_id', 'UNKNOWN')
            return {
                'status': 'HUMAN_APPROVED',
                'approver': reviewer_id,
                'reason': f'Human reviewer approved invoice (${amount:,.2f})',
                'workflow_status': 'APPROVED'
            }
        
        # Policy 2: Check vendor approval status
        vendor_info = state.get('vendor_info', {})
        if not vendor_info.get('is_approved_vendor', False):
            return {
                'status': 'REJECTED',
                'approver': 'SYSTEM',
                'reason': 'Vendor is not in approved vendor list',
                'workflow_status': 'APPROVAL_REJECTED'
            }
        
        # Policy 3: Check validation errors
        validation_errors = state.get('validation_errors', [])
        if validation_errors:
            return {
                'status': 'REQUIRES_APPROVAL',
                'approver': 'PENDING',
                'reason': f'Invoice has {len(validation_errors)} validation errors',
                'workflow_status': 'PENDING_APPROVAL'
            }
        
        # Default: Auto-approve if matched and vendor is approved
        return {
            'status': 'AUTO_APPROVED',
            'approver': 'SYSTEM',
            'reason': f'Invoice matched and vendor approved (${amount:,.2f})',
            'workflow_status': 'APPROVED'
        }


# Create node instance
approve_node = ApproveNode()

