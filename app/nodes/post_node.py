"""
POST Node - Post invoice to ERP system
"""
from typing import Dict, Any
from datetime import datetime
import uuid

from app.nodes.base_node import DeterministicNode
from core.models.state import InvoiceState
from integrations.tools.bigtool_picker import bigtool_picker
from core.utils.error_handler import ERPError, with_retry, RetryPolicy
from core.utils.logging_config import get_logger
from integrations.mcp.atlas_mcp_client import get_atlas_client

logger = get_logger(__name__)


class PostNode(DeterministicNode):
    """
    POST node: Post approved invoice to ERP system
    
    Responsibilities:
    - Use BigtoolPicker to select ERP connector
    - Post invoice data to ERP
    - Post accounting entries to GL
    - Update vendor balance
    - Record ERP transaction ID
    - Handle posting errors with retry
    """
    
    def __init__(self):
        super().__init__(
            name="POST",
            retry_policy=RetryPolicy(max_retries=3, backoff_seconds=2.0)
        )
    
    def execute(self, state: InvoiceState) -> InvoiceState:
        """
        Execute POST logic
        
        Args:
            state: Current workflow state
            
        Returns:
            Updated state with erp_transaction_id, posting_status, posted_at
        """
        logger.info("Starting ERP posting")
        
        # Validate required fields
        self.validate_required_fields(state, ['invoice_id', 'extracted_data', 'accounting_entries'])
        
        # Check approval status
        approval_status = state.get('approval_status')
        if approval_status not in ['AUTO_APPROVED', 'HUMAN_APPROVED']:
            logger.warning(f"Invoice not approved, skipping posting: {approval_status}")
            state['posting_status'] = 'SKIPPED'
            state['posting_message'] = f'Invoice not approved (status: {approval_status})'
            state['status'] = 'POSTING_SKIPPED'
            return state
        
        invoice_id = state['invoice_id']
        extracted_data = state['extracted_data']
        accounting_entries = state['accounting_entries']
        
        # Select ERP connector
        erp_tool = bigtool_picker.select('erp_connector')
        logger.info(f"Selected ERP connector: {erp_tool['name']}")
        
        # Post to ERP using ATLAS MCP
        try:
            atlas = get_atlas_client()
            posting_result = atlas.post_to_erp(
                invoice_data={'invoice_id': invoice_id, **extracted_data},
                accounting_entries=accounting_entries
            )
            
            # Map ATLAS result to expected format
            posting_result = {
                'transaction_id': posting_result.get('erp_txn_id'),
                'status': 'SUCCESS' if posting_result.get('posted') else 'FAILED',
                'message': f"Successfully posted to {erp_tool['name']}",
                'posted_at': posting_result.get('posted_at', datetime.utcnow().isoformat())
            }
            
            # Update state
            state['erp_transaction_id'] = posting_result['transaction_id']
            state['posting_status'] = posting_result['status']
            state['posting_message'] = posting_result['message']
            state['posted_at'] = posting_result['posted_at']
            state['erp_tool_used'] = erp_tool['name']
            state['status'] = 'POSTED'
            
            logger.info(
                f"Posting complete - Transaction ID: {posting_result['transaction_id']}, "
                f"Status: {posting_result['status']}"
            )
            
        except Exception as e:
            logger.error(f"Failed to post to ERP: {e}")
            state['posting_status'] = 'FAILED'
            state['posting_message'] = str(e)
            state['status'] = 'POSTING_FAILED'
            raise ERPError(
                f"Failed to post invoice to ERP: {e}",
                node="POST",
                recoverable=True
            )
        
        return state
    
    @with_retry(retry_policy=RetryPolicy(max_retries=2, backoff_seconds=2.0))
    def _post_to_erp(
        self,
        invoice_id: str,
        invoice_data: Dict[str, Any],
        accounting_entries: list,
        erp_tool: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Post invoice and accounting entries to ERP
        
        Args:
            invoice_id: Invoice identifier
            invoice_data: Extracted invoice data
            accounting_entries: List of accounting entries
            erp_tool: Selected ERP tool info
            
        Returns:
            Dictionary with posting result
        """
        tool_name = erp_tool['name']
        
        # Mock ERP posting
        # In production, this would call actual ERP API
        logger.info(f"Posting invoice {invoice_id} to {tool_name}")
        
        # Generate ERP transaction ID
        transaction_id = f"ERP-TXN-{uuid.uuid4().hex[:12].upper()}"
        
        # Simulate posting invoice header
        invoice_header = {
            'invoice_id': invoice_id,
            'vendor_name': invoice_data.get('vendor_name'),
            'invoice_number': invoice_data.get('invoice_number'),
            'invoice_date': invoice_data.get('invoice_date'),
            'due_date': invoice_data.get('due_date'),
            'total_amount': invoice_data.get('total_amount'),
            'currency': 'USD',
            'status': 'POSTED'
        }
        
        logger.info(f"Posted invoice header: {invoice_header['invoice_number']}")
        
        # Simulate posting line items
        line_items = invoice_data.get('line_items', [])
        for i, item in enumerate(line_items, 1):
            logger.info(
                f"Posted line item {i}: {item.get('description')} - "
                f"${item.get('amount', 0):,.2f}"
            )
        
        # Simulate posting accounting entries
        for entry in accounting_entries:
            logger.info(
                f"Posted GL entry: {entry['account_code']} - "
                f"DR: ${entry['debit']:,.2f}, CR: ${entry['credit']:,.2f}"
            )
        
        # Simulate updating vendor balance
        vendor_name = invoice_data.get('vendor_name')
        total_amount = invoice_data.get('total_amount', 0)
        logger.info(f"Updated vendor balance for {vendor_name}: +${total_amount:,.2f}")
        
        # Return posting result
        return {
            'transaction_id': transaction_id,
            'status': 'SUCCESS',
            'message': f'Successfully posted invoice to {tool_name}',
            'posted_at': datetime.utcnow().isoformat(),
            'invoice_posted': True,
            'gl_entries_posted': len(accounting_entries),
            'vendor_balance_updated': True
        }


# Create node instance
post_node = PostNode()

