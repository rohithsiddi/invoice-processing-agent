"""
COMPLETE Node - Finalize workflow and create audit payload
"""
from typing import Dict, Any
from datetime import datetime

from app.nodes.base_node import DeterministicNode
from core.models.state import InvoiceState
from core.models.database import get_session, Invoice, AuditLog
from core.utils.helpers import calculate_hash
from core.utils.logging_config import get_logger

logger = get_logger(__name__)


class CompleteNode(DeterministicNode):
    """
    COMPLETE node: Finalize workflow and create comprehensive audit payload
    
    Responsibilities:
    - Create final payload with all workflow data
    - Save invoice to database
    - Create audit trail
    - Calculate processing metrics
    - Mark workflow as complete
    """
    
    def __init__(self):
        super().__init__(name="COMPLETE")
    
    def execute(self, state: InvoiceState) -> InvoiceState:
        """
        Execute COMPLETE logic
        
        Args:
            state: Current workflow state
            
        Returns:
            Updated state with final_payload, completion_timestamp, workflow_complete
        """
        logger.info("Starting workflow completion")
        
        # Validate required fields
        self.validate_required_fields(state, ['invoice_id', 'status'])
        
        invoice_id = state['invoice_id']
        
        # Create final payload
        final_payload = self._create_final_payload(state)
        
        # Save final output to JSON file
        try:
            self._save_final_output_json(invoice_id, final_payload)
        except Exception as e:
            logger.warning(f"Failed to save final output JSON: {e}")
            # Continue even if JSON save fails
        
        # Save to database
        try:
            self._save_to_database(state, final_payload)
        except Exception as e:
            logger.error(f"Failed to save to database: {e}")
            # Continue even if database save fails
        
        # Calculate metrics
        metrics = self._calculate_metrics(state)
        
        # Update state
        state['final_payload'] = final_payload
        state['completion_timestamp'] = datetime.utcnow().isoformat()
        state['workflow_complete'] = True
        state['processing_metrics'] = metrics
        state['status'] = 'COMPLETED'
        
        logger.info(
            f"Workflow complete - Invoice: {invoice_id}, "
            f"Duration: {metrics.get('total_duration_seconds', 0):.2f}s, "
            f"Nodes: {metrics.get('nodes_executed', 0)}"
        )
        
        return state
    
    def _create_final_payload(self, state: InvoiceState) -> Dict[str, Any]:
        """
        Create comprehensive final payload
        
        Args:
            state: Current workflow state
            
        Returns:
            Final payload dictionary
        """
        payload = {
            'invoice_id': state['invoice_id'],
            'workflow_status': state['status'],
            'completion_timestamp': datetime.utcnow().isoformat(),
            
            # Invoice data
            'invoice_data': {
                'vendor_name': state.get('extracted_data', {}).get('vendor_name'),
                'invoice_number': state.get('extracted_data', {}).get('invoice_number'),
                'invoice_date': state.get('extracted_data', {}).get('invoice_date'),
                'due_date': state.get('extracted_data', {}).get('due_date'),
                'total_amount': state.get('extracted_data', {}).get('total_amount'),
                'currency': 'USD',
                'line_items': state.get('extracted_data', {}).get('line_items', [])
            },
            
            # Processing results
            'processing_results': {
                'ocr_confidence': state.get('confidence_score'),
                'invoice_type': state.get('invoice_type'),
                'validation_passed': state.get('is_valid'),
                'validation_errors': state.get('validation_errors', []),
                'match_score': state.get('match_score'),
                'match_result': state.get('match_result')
            },
            
            # Approval & posting
            'approval_posting': {
                'approval_status': state.get('approval_status'),
                'approver': state.get('approver'),
                'approval_reason': state.get('approval_reason'),
                'posting_status': state.get('posting_status'),
                'erp_transaction_id': state.get('erp_transaction_id'),
                'posted_at': state.get('posted_at')
            },
            
            # Human review (if applicable)
            'human_review': {
                'review_required': state.get('hitl_checkpoint_id') is not None,
                'hitl_checkpoint_id': state.get('hitl_checkpoint_id'),
                'human_decision': state.get('human_decision'),
                'reviewer_id': state.get('reviewer_id'),
                'review_notes': state.get('review_notes')
            },
            
            # Accounting
            'accounting': {
                'entries': state.get('accounting_entries', []),
                'reconciliation_report': state.get('reconciliation_report')
            },
            
            # Vendor info
            'vendor_info': {
                'vendor_id': state.get('vendor_info', {}).get('vendor_id'),
                'vendor_category': state.get('vendor_info', {}).get('vendor_category'),
                'is_approved_vendor': state.get('vendor_info', {}).get('is_approved_vendor')
            },
            
            # Notifications
            'notifications': {
                'notification_sent': True,  
                'notification_type': state.get('notification_type', 'SUCCESS' if state['status'] == 'COMPLETED' else 'APPROVAL_NEEDED'),
                'notification_recipients': state.get('notification_recipients', ['rohithsiddi7@gmail.com'])
            },
            
            # Metadata
            'metadata': {
                'created_at': state.get('created_at'),
                'updated_at': state.get('updated_at'),
                'file_path': state.get('file_path'),
                'file_type': state.get('file_type'),
                'file_size': state.get('file_size')
            }
        }
        
        # Add payload hash for integrity
        payload['payload_hash'] = calculate_hash(payload)
        
        return payload
    
    def _save_to_database(self, state: InvoiceState, payload: Dict[str, Any]):
        """
        Save invoice and audit trail to database
        
        Args:
            state: Current workflow state
            payload: Final payload
        """
        session = get_session()
        try:
            # Save/update invoice record
            invoice_id = state['invoice_id']
            extracted_data = state.get('extracted_data', {})
            
            invoice = session.query(Invoice).filter(
                Invoice.invoice_id == invoice_id
            ).first()
            
            if not invoice:
                invoice = Invoice(
                    invoice_id=invoice_id,
                    file_path=state.get('file_path', 'N/A'),
                    file_type=state.get('file_type', 'pdf')
                )
                session.add(invoice)
            
            # Update invoice fields
            invoice.file_path = state.get('file_path', invoice.file_path or 'N/A')
            invoice.file_type = state.get('file_type', invoice.file_type or 'pdf')
            invoice.vendor_name = extracted_data.get('vendor_name')
            invoice.invoice_number = extracted_data.get('invoice_number')
            invoice.invoice_date = extracted_data.get('invoice_date')
            invoice.total_amount = extracted_data.get('total_amount')
            invoice.extracted_data = extracted_data
            invoice.confidence_score = state.get('confidence_score')
            invoice.invoice_type = state.get('invoice_type')
            invoice.is_valid = state.get('is_valid', False)
            invoice.validation_errors = state.get('validation_errors')
            invoice.match_score = state.get('match_score')
            invoice.match_result = state.get('match_result')
            invoice.matched_po_number = state.get('matched_po_number')
            invoice.status = state['status']
            invoice.approval_status = state.get('approval_status')
            invoice.erp_transaction_id = state.get('erp_transaction_id')
            invoice.updated_at = datetime.utcnow()
            
            # Create audit log
            audit_log = AuditLog(
                invoice_id=invoice_id,
                node_name='COMPLETE',
                action='WORKFLOW_COMPLETED',
                details=f"Workflow completed with status: {state['status']}",
                timestamp=datetime.utcnow()
            )
            session.add(audit_log)
            
            session.commit()
            logger.info(f"Saved invoice and audit log to database: {invoice_id}")
            
        except Exception as e:
            session.rollback()
            logger.error(f"Database save failed: {e}")
            raise
        finally:
            session.close()
    
    def _save_final_output_json(self, invoice_id: str, payload: Dict[str, Any]):
        """
        Save final output to JSON file in outputs folder
        
        Args:
            invoice_id: Invoice ID
            payload: Final payload dictionary
        """
        import json
        from pathlib import Path
        
        # Create outputs directory if it doesn't exist
        outputs_dir = Path("outputs")
        outputs_dir.mkdir(exist_ok=True)
        
        # Get invoice number from payload, fallback to invoice ID
        invoice_number = payload.get('invoice_data', {}).get('invoice_number', invoice_id)
        # Clean invoice number for filename (remove special characters)
        safe_invoice_number = invoice_number.replace('/', '_').replace('\\', '_')
        
        # Create filename with invoice number
        output_file = outputs_dir / f"{safe_invoice_number}_final_output.json"
        
        # Save JSON file
        with open(output_file, 'w') as f:
            json.dump(payload, f, indent=2)
        
        logger.info(f"✅ Final output saved to: {output_file}")
    
    def _calculate_metrics(self, state: InvoiceState) -> Dict[str, Any]:
        """
        Calculate processing metrics
        
        Args:
            state: Current workflow state
            
        Returns:
            Metrics dictionary
        """
        created_at = state.get('created_at')
        completion_time = datetime.utcnow()
        
        # Calculate duration
        if created_at:
            from core.utils.helpers import parse_date
            created_dt = parse_date(created_at) if isinstance(created_at, str) else created_at
            if created_dt:
                duration = (completion_time - created_dt).total_seconds()
            else:
                duration = 0
        else:
            duration = 0
        
        # Count nodes executed (estimate from state keys)
        nodes_executed = 0
        node_indicators = [
            'ingested_at', 'extracted_data', 'invoice_type',
            'vendor_info', 'validation_errors', 'matched_pos',
            'match_score', 'accounting_entries', 'approval_status',
            'erp_transaction_id', 'notification_sent'
        ]
        for indicator in node_indicators:
            if indicator in state:
                nodes_executed += 1
        
        return {
            'total_duration_seconds': duration,
            'nodes_executed': nodes_executed,
            'completion_timestamp': completion_time.isoformat(),
            'workflow_status': state['status'],
            'human_intervention_required': state.get('hitl_checkpoint_id') is not None,
            'auto_approved': state.get('approval_status') == 'AUTO_APPROVED',
            'successfully_posted': state.get('posting_status') == 'SUCCESS'
        }


# Create node instance
complete_node = CompleteNode()

