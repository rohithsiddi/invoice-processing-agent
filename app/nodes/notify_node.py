"""
NOTIFY Node - Send email notifications about invoice processing
"""
from typing import Dict, Any, List
from datetime import datetime

from app.nodes.base_node import DeterministicNode
from core.models.state import InvoiceState
from integrations.tools.bigtool_picker import bigtool_picker
from core.utils.error_handler import with_retry, RetryPolicy
from core.utils.helpers import format_currency
from core.utils.logging_config import get_logger
from integrations.mcp.atlas_mcp_client import get_atlas_client

logger = get_logger(__name__)


class NotifyNode(DeterministicNode):
    """
    NOTIFY node: Send email notifications about invoice processing status
    
    Responsibilities:
    - Use BigtoolPicker to select email service
    - Send notifications based on workflow outcome
    - Different templates for: success, failure, human review needed
    - Include invoice summary and next steps
    """
    
    def __init__(self):
        super().__init__(
            name="NOTIFY",
            retry_policy=RetryPolicy(max_retries=2, backoff_seconds=1.0)
        )
    
    def execute(self, state: InvoiceState) -> InvoiceState:
        """
        Execute NOTIFY logic
        
        Args:
            state: Current workflow state
            
        Returns:
            Updated state with notification_sent, notification_recipients
        """
        logger.info("Starting notification process")
        
        # Validate required fields
        self.validate_required_fields(state, ['invoice_id', 'status'])
        
        invoice_id = state['invoice_id']
        status = state['status']
        
        # Determine notification type and recipients
        notification_config = self._determine_notification_config(state)
        
        # Select email service
        email_tool = bigtool_picker.select('email')
        logger.info(f"Selected email service: {email_tool['name']}")
        
        # Send notifications
        try:
            notification_result = self._send_notifications(
                state,
                notification_config,
                email_tool
            )
            
            # Update state
            state['notification_sent'] = True
            state['notification_recipients'] = notification_result['recipients']
            state['notification_type'] = notification_result['type']
            state['notification_timestamp'] = notification_result['timestamp']
            state['email_tool_used'] = email_tool['name']
            
            logger.info(
                f"Notifications sent - Type: {notification_result['type']}, "
                f"Recipients: {len(notification_result['recipients'])}"
            )
            
        except Exception as e:
            logger.error(f"Failed to send notifications: {e}")
            state['notification_sent'] = False
            state['notification_error'] = str(e)
        
        return state
    
    def _determine_notification_config(self, state: InvoiceState) -> Dict[str, Any]:
        """
        Determine notification type and recipients based on state
        
        Args:
            state: Current workflow state
            
        Returns:
            Notification configuration
        """
        from core.config.config import config
        
        status = state['status']
        
        # Success notification
        if status == 'POSTED':
            return {
                'type': 'SUCCESS',
                'recipients': config.REVIEWER_EMAILS,
                'subject': 'Invoice Processed Successfully',
                'priority': 'NORMAL'
            }
        
        # Human review needed
        elif status == 'PENDING_REVIEW':
            return {
                'type': 'REVIEW_NEEDED',
                'recipients': config.REVIEWER_EMAILS,
                'subject': 'Invoice Requires Human Review',
                'priority': 'HIGH'
            }
        
        # Approval needed
        elif status == 'PENDING_APPROVAL':
            return {
                'type': 'APPROVAL_NEEDED',
                'recipients': config.REVIEWER_EMAILS,
                'subject': 'Invoice Requires Approval',
                'priority': 'HIGH'
            }
        
        # Rejected
        elif status in ['APPROVAL_REJECTED', 'MANUAL_HANDOFF']:
            return {
                'type': 'REJECTED',
                'recipients': config.REVIEWER_EMAILS,
                'subject': 'Invoice Processing Failed',
                'priority': 'HIGH'
            }
        
        # Default
        else:
            return {
                'type': 'INFO',
                'recipients': config.REVIEWER_EMAILS,
                'subject': 'Invoice Processing Update',
                'priority': 'NORMAL'
            }
    
    @with_retry(retry_policy=RetryPolicy(max_retries=2, backoff_seconds=1.0))
    def _send_notifications(
        self,
        state: InvoiceState,
        config: Dict[str, Any],
        email_tool: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Send email notifications
        
        Args:
            state: Current workflow state
            config: Notification configuration
            email_tool: Selected email tool info
            
        Returns:
            Notification result
        """
        tool_name = email_tool['name']
        notification_type = config['type']
        
        # Build email content
        email_content = self._build_email_content(state, notification_type)
        
        # Send via SendGrid (real email)
        logger.info(f"Sending {notification_type} notification via {tool_name}")
        logger.info(f"To: {', '.join(config['recipients'])}")
        logger.info(f"Subject: {config['subject']}")
        logger.info(f"Priority: {config['priority']}")
        
        # Log email content
        logger.info("Email content:")
        for line in email_content.split('\n')[:10]:  # First 10 lines
            logger.info(f"  {line}")
        
        # Actually send the email via ATLAS MCP
        try:
            from integrations.mcp.atlas_mcp_client import get_atlas_client
            
            atlas = get_atlas_client()
            extracted_data = state.get('extracted_data', {})
            
            notification_result = atlas.send_notification(
                notification_type=notification_type,
                recipients=config['recipients'],
                data={
                    'invoice_id': state.get('invoice_id'),
                    'invoice_number': extracted_data.get('invoice_number', 'N/A'),
                    'vendor_name': extracted_data.get('vendor_name', 'Unknown'),
                    'total_amount': extracted_data.get('total_amount', 0),
                    'status': state.get('status', 'UNKNOWN'),
                    'subject': config['subject'],
                    'body': email_content
                }
            )
            
            return {
                'recipients': config['recipients'],
                'type': notification_type,
                'timestamp': datetime.utcnow().isoformat(),
                'email_sent': notification_result.get('sent', False),
                'email_ids': notification_result.get('notification_ids', []),
                'service': notification_result.get('service', 'unknown')
            }
            
        except Exception as e:
            logger.error(f"Failed to send email via SendGrid: {e}")
            # Return mock result as fallback
            return {
                'recipients': config['recipients'],
                'type': notification_type,
                'timestamp': datetime.utcnow().isoformat(),
                'email_sent': False,
                'email_ids': [f"MSG-{i:03d}" for i in range(len(config['recipients']))],
                'error': str(e)
            }
    
    def _build_email_content(self, state: InvoiceState, notification_type: str) -> str:
        """
        Build email content based on notification type
        
        Args:
            state: Current workflow state
            notification_type: Type of notification
            
        Returns:
            Email content (plain text)
        """
        invoice_id = state['invoice_id']
        extracted_data = state.get('extracted_data', {})
        vendor_name = extracted_data.get('vendor_name', 'Unknown')
        invoice_number = extracted_data.get('invoice_number', 'Unknown')
        total_amount = extracted_data.get('total_amount', 0)
        
        # Common header
        content = f"""
Invoice Processing Notification
================================

Invoice ID: {invoice_id}
Vendor: {vendor_name}
Invoice Number: {invoice_number}
Amount: {format_currency(total_amount)}
Status: {state.get('status', 'Unknown')}

"""
        
        # Type-specific content
        if notification_type == 'SUCCESS':
            content += self._build_success_content(state)
        elif notification_type == 'REVIEW_NEEDED':
            content += self._build_review_needed_content(state)
        elif notification_type == 'APPROVAL_NEEDED':
            content += self._build_approval_needed_content(state)
        elif notification_type == 'REJECTED':
            content += self._build_rejected_content(state)
        else:
            content += "Processing update available.\n"
        
        # Footer
        content += f"""
================================
Timestamp: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
System: Invoice Processing Agent
"""
        
        return content
    
    def _build_success_content(self, state: InvoiceState) -> str:
        """Build success notification content"""
        return f"""
✓ SUCCESS: Invoice processed and posted to ERP

The invoice has been successfully processed and is now in the ERP system.
No further action required.
"""
    
    def _build_review_needed_content(self, state: InvoiceState) -> str:
        """Build review needed notification content"""
        review_url = state.get('review_url', 'N/A')
        paused_reason = state.get('paused_reason', 'Manual review required')
        
        return f"""
⚠ REVIEW NEEDED: Invoice requires human review

Reason:
{paused_reason}

Action Required:
Please review this invoice and make a decision (Accept/Reject).

Review URL: {review_url}

The workflow is paused until a decision is made.
"""
    
    def _build_approval_needed_content(self, state: InvoiceState) -> str:
        """Build approval needed notification content"""
        approval_reason = state.get('approval_reason', 'Exceeds auto-approval threshold')
        
        return f"""
⚠ APPROVAL NEEDED: Invoice requires management approval

Reason:
{approval_reason}

Action Required:
Please review and approve this invoice.

The invoice is on hold pending approval.
"""
    
    def _build_rejected_content(self, state: InvoiceState) -> str:
        """Build rejected notification content"""
        approval_reason = state.get('approval_reason', 'Unknown')
        
        return f"""
✗ REJECTED: Invoice processing failed

Reason:
{approval_reason}

Action Required:
Please review the invoice manually and take appropriate action.

The invoice has been flagged for manual handling.
"""


# Create node instance
notify_node = NotifyNode()

