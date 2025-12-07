"""
ATLAS MCP Client - Mock Data Only
Uses sample JSON data from data/samples/
"""
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from core.utils.logging_config import get_logger

logger = get_logger(__name__)


class RealATLASMCPClient:
    """
    ATLAS MCP Client - Mock Implementation
    
    Uses sample JSON data for POs, GRNs, and historical invoices
    """
    
    def __init__(self):
        """Initialize ATLAS MCP client with mock data"""
        self.sample_data_dir = Path("data/samples")
        logger.info(f"Initializing ATLAS MCP Client (Mock Mode)")
        logger.info(f"Using sample data from {self.sample_data_dir}")
    
    def _load_mock_data(self, filename: str) -> Any:
        """Load mock data from JSON file"""
        file_path = self.sample_data_dir / filename
        if not file_path.exists():
            logger.error(f"Mock data file not found: {file_path}")
            return None
        
        with open(file_path, 'r') as f:
            return json.load(f)
    
    def fetch_po(self, vendor_id: str = None, vendor_name: str = None, amount: float = None) -> List[Dict[str, Any]]:
        """
        Fetch purchase orders from mock data
        
        Args:
            vendor_id: Vendor ID (unused in mock)
            vendor_name: Vendor name
            amount: Amount to match
            
        Returns:
            List of matching POs
        """
        logger.info("=" * 60)
        logger.info("ATLAS MCP - Fetching Purchase Orders")
        logger.info("=" * 60)
        logger.info(f"Vendor: {vendor_name or vendor_id}")
        logger.info(f"Amount: ${amount}" if amount else "Amount: Any")
        
        # Use mock data
        logger.info("Using mock data")
        po_data = self._load_mock_data("sample_po.json")
        
        if not po_data:
            return []
        
        # Filter by vendor
        if vendor_name and po_data.get('vendor_name') != vendor_name:
            logger.info(f"No PO found for vendor: {vendor_name}")
            return []
        
        # Filter by amount (with 10% tolerance)
        if amount:
            po_amount = po_data.get('total_amount', 0)
            tolerance = amount * 0.1
            if abs(po_amount - amount) > tolerance:
                logger.info(f"PO amount ${po_amount} doesn't match invoice ${amount}")
                return []
            
        logger.info(f"Found PO: {po_data.get('po_number')}")
        logger.info("=" * 60)
        return [po_data]
    
    
    def fetch_grn(self, po_number: str = None, vendor_id: str = None) -> List[Dict[str, Any]]:
        """
        Fetch goods receipt notes from mock data
        
        Args:
            po_number: PO number
            vendor_id: Vendor ID (unused in mock)
            
        Returns:
            List of matching GRNs
        """
        logger.info("=" * 60)
        logger.info("ATLAS MCP - Fetching Goods Receipt Notes")
        logger.info("=" * 60)
        logger.info(f"PO Number: {po_number}" if po_number else "PO Number: Any")
        
        # Use mock data
        logger.info("Using mock data")
        grn_data = self._load_mock_data("sample_grn.json")
        
        if not grn_data:
            return []
        
        # Filter by PO number
        if po_number and grn_data.get('po_number') != po_number:
            logger.info(f"No GRN found for PO: {po_number}")
            return []
        
        logger.info(f"Found GRN: {grn_data.get('grn_number')}")
        logger.info("=" * 60)
        return [grn_data]
    
    
    def fetch_history(self, vendor_id: str = None, vendor_name: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch historical invoices
        
        Args:
            vendor_id: Vendor ID
            vendor_name: Vendor name
            limit: Max records
            
        Returns:
            List of historical invoices
        """
        logger.info("=" * 60)
        logger.info("ATLAS MCP - Fetching Historical Invoices")
        logger.info("=" * 60)
        logger.info(f"Vendor: {vendor_name or vendor_id}")
        logger.info(f"Limit: {limit}")
        
        # Always use mock data
        logger.info("Using mock data")
        history_data = self._load_mock_data("sample_history.json")
        
        if not history_data:
            return []
        
            # Filter by vendor
        if vendor_name:
            history_data = [inv for inv in history_data if inv.get('vendor_name') == vendor_name]
        
            # Limit results
        history_data = history_data[:limit]
        
        logger.info(f"Found {len(history_data)} historical invoices")
        logger.info("=" * 60)
        return history_data
    
    def enrich_vendor(self, vendor_name: str) -> Dict[str, Any]:
        """
        Enrich vendor data with external information
        
        ATLAS MCP Tool: enrich_vendor
        
        Args:
            vendor_name: Vendor name to enrich
            
        Returns:
            Enriched vendor data
        """
        logger.info("=" * 60)
        logger.info("ATLAS MCP - Enriching Vendor Data")
        logger.info("=" * 60)
        logger.info(f"Vendor: {vendor_name}")
        
        # Use mock enrichment data
        logger.info("Using mock enrichment data")
        
        # Map vendor names to IDs (matching sample_po.json)
        vendor_mapping = {
            "ABC Corporation": "VND-ABC-001",
            "XYZ Industries": "VND-XYZ-002",
            "Tech Solutions Inc": "VND-TECH-003"
        }
        
        # Get vendor ID from mapping or generate one
        vendor_id = vendor_mapping.get(vendor_name)
        if not vendor_id:
            import hashlib
            vendor_id = "VND-" + hashlib.md5(vendor_name.encode()).hexdigest()[:8].upper()
        
        tax_id = f"{hash(vendor_name) % 90 + 10}-{hash(vendor_name[::-1]) % 9000000 + 1000000}"
        
        enriched_data = {
            'vendor_id': vendor_id,
            'vendor_name': vendor_name,
            'tax_id': tax_id,
            'credit_score': 750,
            'risk_score': 0.15,
            'payment_terms': 'Net 30',
            'is_approved_vendor': True,
            'credit_limit': 50000.00,
            'enrichment_source': 'mock_vendor_db'
        }
        
        logger.info(f"Enriched vendor: {vendor_id}")
        logger.info("=" * 60)
        return enriched_data
    
        
        try:
            logger.info("Calling real ATLAS MCP server")
            result = asyncio.run(self._call_mcp_tool_async("enrich_vendor", {
                "vendor_name": vendor_name
            }))
            logger.info("Vendor enrichment successful")
            logger.info("=" * 60)
            return result
        except Exception as e:
            logger.error(f"MCP call failed: {e}")
            logger.warning("Falling back to mock data")
            return self.enrich_vendor(vendor_name)
    
    def post_to_erp(self, invoice_data: Dict[str, Any], accounting_entries: List[Dict]) -> Dict[str, Any]:
        """
        Post invoice and accounting entries to ERP system
        
        ATLAS MCP Tool: post_to_erp
        
        Args:
            invoice_data: Invoice data to post
            accounting_entries: GL entries
            
        Returns:
            Posting result with transaction IDs
        """
        logger.info("=" * 60)
        logger.info("ATLAS MCP - Posting to ERP")
        logger.info("=" * 60)
        logger.info(f"Invoice: {invoice_data.get('invoice_id')}")
        logger.info(f"Amount: ${invoice_data.get('total_amount')}")
        logger.info(f"Entries: {len(accounting_entries)}")
        
        # Always use mock data
        logger.info("Using mock ERP posting")
        import uuid
        
        result = {
            'posted': True,
            'erp_txn_id': f"ERP-TXN-{uuid.uuid4().hex[:8].upper()}",
            'scheduled_payment_id': f"PAY-{uuid.uuid4().hex[:8].upper()}",
            'posted_at': '2025-12-07T10:54:00Z',
            'erp_system': 'mock_erp'
        }
        
        logger.info(f"Posted successfully: {result['erp_txn_id']}")
        logger.info("=" * 60)
        return result
        
        try:
            logger.info("Calling real ATLAS MCP server")
            result = asyncio.run(self._call_mcp_tool_async("post_to_erp", {
                "invoice_data": invoice_data,
                "accounting_entries": accounting_entries
            }))
            logger.info("ERP posting successful")
            logger.info("=" * 60)
            return result
        except Exception as e:
            logger.error(f"MCP call failed: {e}")
            logger.warning("Falling back to mock posting")
            return self.post_to_erp(invoice_data, accounting_entries)
    
    def send_notification(self, notification_type: str, recipients: List[str], data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send notifications via email/messaging
        
        ATLAS MCP Tool: send_notification
        
        Args:
            notification_type: Type of notification
            recipients: List of recipient emails
            data: Notification data
            
        Returns:
            Notification result
        """
        logger.info("=" * 60)
        logger.info("ATLAS MCP - Sending Notifications")
        logger.info("=" * 60)
        logger.info(f"Type: {notification_type}")
        logger.info(f"Recipients: {len(recipients)}")
        
        # Try to use real SendGrid
        import os
        sendgrid_api_key = os.getenv('SENDGRID_API_KEY')
        
        if sendgrid_api_key and sendgrid_api_key.startswith('SG.'):
            try:
                from sendgrid import SendGridAPIClient
                from sendgrid.helpers.mail import Mail, Email, To, Content
                
                logger.info("Using real SendGrid service")
                
                # Get sender info from env
                from_email = os.getenv('SENDGRID_FROM_EMAIL', 'noreply@invoiceprocessing.com')
                from_name = os.getenv('SENDGRID_FROM_NAME', 'Invoice Processing System')
                
                # Build email content
                if 'subject' in data:
                    subject = data['subject']
                else:
                    subject = f'Invoice Processing: {notification_type}'
                
                if 'body' in data:
                    body = data['body']
                else:
                    body = self._build_email_body(notification_type, data)
                
                # Send to each recipient
                notification_ids = []
                
                try:
                    sg = SendGridAPIClient(sendgrid_api_key)
                    
                    for recipient in recipients:
                        message = Mail(
                            from_email=Email(from_email, from_name),
                            to_emails=To(recipient),
                            subject=subject,
                            plain_text_content=Content("text/plain", body)
                        )
                        
                        # Disable click tracking to preserve original URLs
                        from sendgrid.helpers.mail import TrackingSettings, ClickTracking
                        message.tracking_settings = TrackingSettings()
                        message.tracking_settings.click_tracking = ClickTracking(False, False)
                        
                        response = sg.send(message)
                        
                        # Get message ID safely
                        try:
                            msg_id = str(response.headers.get('X-Message-Id', f'NOTIF-{len(notification_ids)+1:03d}'))
                        except:
                            msg_id = f'NOTIF-{len(notification_ids)+1:03d}'
                        
                        notification_ids.append(msg_id)
                        logger.info(f"Email sent to {recipient}: Status {response.status_code}")
                        
                except Exception as e:
                    logger.error(f"SendGrid error: {str(e)}")
                    raise
                
                result = {
                    'sent': True,
                    'notification_ids': notification_ids,
                    'recipients_count': len(recipients),
                    'service': 'sendgrid'
                }
                
                logger.info(f"Notifications sent via SendGrid: {len(recipients)}")
                logger.info("=" * 60)
                return result
                
            except Exception as e:
                logger.error(f"SendGrid failed: {e}")
                logger.warning("Falling back to mock notifications")
        
        # Fallback to mock
        logger.info("Using mock notification service (no SendGrid API key)")
        
        result = {
            'sent': True,
            'notification_ids': [f"NOTIF-{i+1:03d}" for i in range(len(recipients))],
            'recipients_count': len(recipients),
            'service': 'mock_sendgrid'
        }
        
        logger.info(f"Mock notifications sent: {len(recipients)}")
        logger.info("=" * 60)
        return result
    
    def _build_email_body(self, notification_type: str, data: Dict[str, Any]) -> str:
        """Build email body based on notification type"""
        invoice_number = data.get('invoice_number', 'N/A')
        vendor = data.get('vendor_name', 'N/A')
        amount = data.get('total_amount', 0)
        status = data.get('status', 'N/A')
        
        if notification_type == 'SUCCESS':
            return f"""
Invoice Processing Notification
================================

Invoice Number: {invoice_number}
Vendor: {vendor}
Amount: ${amount:,.2f}
Status: {status}

The invoice has been successfully processed and posted to the ERP system.

---
Invoice Processing System
"""
        elif notification_type == 'APPROVAL_NEEDED':
            reason = data.get('reason', 'Manual review required')
            return f"""
Invoice Requires Approval
==========================

Invoice Number: {invoice_number}
Vendor: {vendor}
Amount: ${amount:,.2f}

Reason: {reason}

This invoice requires your approval before processing.

Review URL: http://localhost:8000/review

---
Invoice Processing System
"""
        else:
            return f"""
Invoice Processing Notification
================================

Invoice Number: {invoice_number}
Vendor: {vendor}
Amount: ${amount:,.2f}
Status: {status}
Type: {notification_type}

---
Invoice Processing System
"""
        
        try:
            logger.info("Calling real ATLAS MCP server")
            result = asyncio.run(self._call_mcp_tool_async("send_notification", {
                "notification_type": notification_type,
                "recipients": recipients,
                "data": data
            }))
            logger.info("Notifications sent successfully")
            logger.info("=" * 60)
            return result
        except Exception as e:
            logger.error(f"MCP call failed: {e}")
            logger.warning("Falling back to mock notifications")
            return self.send_notification(notification_type, recipients, data)
    
    def get_human_decision(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """
        Get human review decision from database
        
        ATLAS MCP Tool: get_human_decision
        
        Args:
            checkpoint_id: Checkpoint ID to check
            
        Returns:
            Decision data if available, None otherwise
        """
        logger.info("=" * 60)
        logger.info("ATLAS MCP - Fetching Human Decision")
        logger.info("=" * 60)
        logger.info(f"Checkpoint ID: {checkpoint_id}")
        
        # This always uses local DB (not truly external)
        # But routing through ATLAS MCP as per spec
        from core.models.database import get_session, Checkpoint
        
        session = get_session()
        try:
            checkpoint = session.query(Checkpoint).filter(
                Checkpoint.hitl_checkpoint_id == checkpoint_id
            ).first()
            
            if checkpoint and checkpoint.human_decision:
                result = {
                    'decision': checkpoint.human_decision,
                    'reviewer_id': checkpoint.reviewer_id,
                    'review_notes': checkpoint.review_notes,
                    'reviewed_at': checkpoint.reviewed_at.isoformat() if checkpoint.reviewed_at else None
                }
                logger.info(f"Decision found: {result['decision']}")
                logger.info("=" * 60)
                return result
            else:
                logger.info("No decision found yet")
                logger.info("=" * 60)
                return None
        finally:
            session.close()


# Global client instance
_atlas_client = None


def get_atlas_client() -> 'RealATLASMCPClient':
    """
    Get singleton ATLAS MCP client instance
    
    Returns:
        ATLAS MCP client instance
    """
    global _atlas_client
    
    if _atlas_client is None:
        _atlas_client = RealATLASMCPClient()
    
    return _atlas_client

