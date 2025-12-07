"""
RECONCILE Node - Create accounting entries and reconciliation report
"""
from typing import Dict, Any, List
from datetime import datetime

from app.nodes.base_node import DeterministicNode
from core.models.state import InvoiceState
from core.utils.helpers import format_currency
from core.utils.logging_config import get_logger
from integrations.mcp.common_mcp_client import common_mcp_client

logger = get_logger(__name__)


class ReconcileNode(DeterministicNode):
    """
    RECONCILE node: Create accounting entries if matched or human accepted
    
    Responsibilities:
    - Create journal entries (debits/credits)
    - Debit: Expense/Inventory account
    - Credit: Accounts Payable
    - Generate reconciliation report
    - Calculate variances
    """
    
    def __init__(self):
        super().__init__(name="RECONCILE")
    
    def execute(self, state: InvoiceState) -> InvoiceState:
        """
        Execute RECONCILE logic
        
        Args:
            state: Current workflow state
            
        Returns:
            Updated state with accounting_entries and reconciliation_report
        """
        logger.info("Starting reconciliation")
        
        # Validate required fields
        self.validate_required_fields(state, ['invoice_id', 'extracted_data'])
        
        extracted_data = state['extracted_data']
        match_result = state.get('match_result', 'UNKNOWN')
        matched_po = state.get('matched_po')
        
        # Check if we should reconcile
        # Reconcile if: matched OR human accepted
        human_decision = state.get('human_decision')
        should_reconcile = (match_result == 'MATCHED') or (human_decision == 'ACCEPT')
        
        if not should_reconcile:
            logger.warning("Reconciliation skipped - not matched and not human approved")
            state['accounting_entries'] = []
            state['reconciliation_report'] = {
                'reconciled': False,
                'reason': 'Not matched and not human approved'
            }
            state['status'] = 'RECONCILIATION_SKIPPED'
            return state
        
        # Create accounting entries using COMMON MCP
        accounting_entries = common_mcp_client.build_accounting_entries(
            extracted_data, matched_po or {}
        )
        
        # Generate reconciliation report
        reconciliation_report = self._generate_reconciliation_report(
            extracted_data,
            matched_po,
            match_result
        )
        
        # Update state
        state['accounting_entries'] = accounting_entries
        state['reconciliation_report'] = reconciliation_report
        state['status'] = 'RECONCILED'
        
        logger.info(
            f"Reconciliation complete - Entries: {len(accounting_entries)}, "
            f"Variance: {format_currency(reconciliation_report.get('variance', 0))}"
        )
        
        return state
    
    def _create_accounting_entries(
        self,
        invoice_data: Dict[str, Any],
        po: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Create journal entries for the invoice
        
        Args:
            invoice_data: Extracted invoice data
            po: Matched purchase order (if any)
            
        Returns:
            List of accounting entries
        """
        entries = []
        
        total_amount = invoice_data.get('total_amount', 0)
        subtotal = invoice_data.get('subtotal', total_amount)
        tax_amount = invoice_data.get('tax_amount', 0)
        vendor_name = invoice_data.get('vendor_name', 'Unknown')
        invoice_number = invoice_data.get('invoice_number', 'Unknown')
        
        # Determine account codes based on line items or PO
        expense_account = self._determine_expense_account(invoice_data, po)
        tax_account = '2200'  # Tax Payable
        ap_account = '2000'  # Accounts Payable
        
        # Entry 1: Debit Expense/Inventory
        entries.append({
            'entry_id': f"JE-{invoice_number}-001",
            'account_code': expense_account,
            'account_name': self._get_account_name(expense_account),
            'debit': subtotal,
            'credit': 0.0,
            'description': f"Invoice {invoice_number} from {vendor_name}",
            'reference': invoice_number
        })
        
        # Entry 2: Debit Tax (if applicable)
        if tax_amount > 0:
            entries.append({
                'entry_id': f"JE-{invoice_number}-002",
                'account_code': tax_account,
                'account_name': 'Tax Payable',
                'debit': tax_amount,
                'credit': 0.0,
                'description': f"Tax on invoice {invoice_number}",
                'reference': invoice_number
            })
        
        # Entry 3: Credit Accounts Payable
        entries.append({
            'entry_id': f"JE-{invoice_number}-003",
            'account_code': ap_account,
            'account_name': 'Accounts Payable',
            'debit': 0.0,
            'credit': total_amount,
            'description': f"Payable to {vendor_name} for invoice {invoice_number}",
            'reference': invoice_number,
            'vendor': vendor_name
        })
        
        # Verify entries balance
        total_debits = sum(e['debit'] for e in entries)
        total_credits = sum(e['credit'] for e in entries)
        
        if abs(total_debits - total_credits) > 0.01:
            logger.error(
                f"Accounting entries do not balance! "
                f"Debits: {total_debits}, Credits: {total_credits}"
            )
        else:
            logger.info(f"Accounting entries balanced: {format_currency(total_debits)}")
        
        return entries
    
    def _determine_expense_account(
        self,
        invoice_data: Dict[str, Any],
        po: Dict[str, Any] = None
    ) -> str:
        """
        Determine the appropriate expense account code
        
        Args:
            invoice_data: Invoice data
            po: Purchase order data
            
        Returns:
            Account code
        """
        # In production, this would use sophisticated logic or lookup tables
        # For now, simple categorization based on description
        
        line_items = invoice_data.get('line_items', [])
        
        if line_items:
            first_item = line_items[0]
            desc = first_item.get('description', '').lower()
            
            if any(word in desc for word in ['service', 'consulting', 'professional']):
                return '6100'  # Professional Services Expense
            elif any(word in desc for word in ['software', 'license', 'subscription']):
                return '6200'  # Software & IT Expense
            elif any(word in desc for word in ['material', 'supply', 'equipment']):
                return '5000'  # Inventory/Materials
            else:
                return '6000'  # General Expense
        
        return '6000'  # Default: General Expense
    
    def _get_account_name(self, account_code: str) -> str:
        """Get account name from code"""
        account_names = {
            '5000': 'Inventory/Materials',
            '6000': 'General Expense',
            '6100': 'Professional Services Expense',
            '6200': 'Software & IT Expense',
            '2000': 'Accounts Payable',
            '2200': 'Tax Payable'
        }
        return account_names.get(account_code, 'Unknown Account')
    
    def _generate_reconciliation_report(
        self,
        invoice_data: Dict[str, Any],
        po: Dict[str, Any] = None,
        match_result: str = 'UNKNOWN'
    ) -> Dict[str, Any]:
        """
        Generate reconciliation report
        
        Args:
            invoice_data: Invoice data
            po: Purchase order data
            match_result: Match result
            
        Returns:
            Reconciliation report
        """
        report = {
            'reconciled': True,
            'reconciliation_date': datetime.utcnow().isoformat(),
            'match_type': '2-way' if po else 'manual',
            'match_result': match_result
        }
        
        invoice_amount = invoice_data.get('total_amount', 0)
        
        if po:
            po_amount = po.get('total_amount', 0)
            variance = invoice_amount - po_amount
            variance_pct = (abs(variance) / po_amount * 100) if po_amount > 0 else 0
            
            report.update({
                'po_number': po.get('po_number'),
                'invoice_amount': invoice_amount,
                'po_amount': po_amount,
                'variance': variance,
                'variance_pct': variance_pct,
                'within_tolerance': variance_pct <= 5.0,  # 5% tolerance
                'variance_reason': self._determine_variance_reason(variance, invoice_data, po)
            })
            
            # Line item reconciliation
            if 'line_items' in invoice_data and 'line_items' in po:
                report['line_item_reconciliation'] = self._reconcile_line_items(
                    invoice_data['line_items'],
                    po['line_items']
                )
        else:
            report.update({
                'invoice_amount': invoice_amount,
                'variance': 0.0,
                'variance_pct': 0.0,
                'within_tolerance': True,
                'variance_reason': 'No PO - manual approval'
            })
        
        return report
    
    def _determine_variance_reason(
        self,
        variance: float,
        invoice_data: Dict[str, Any],
        po: Dict[str, Any]
    ) -> str:
        """Determine reason for variance"""
        if abs(variance) < 0.01:
            return 'Perfect match'
        
        invoice_tax = invoice_data.get('tax_amount', 0)
        po_tax = po.get('tax_amount', 0)
        
        if abs(variance - (invoice_tax - po_tax)) < 0.01:
            return 'Tax difference'
        
        if variance > 0:
            return f'Invoice higher by {format_currency(variance)}'
        else:
            return f'Invoice lower by {format_currency(abs(variance))}'
    
    def _reconcile_line_items(
        self,
        invoice_items: List[Dict[str, Any]],
        po_items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Reconcile line items between invoice and PO"""
        matched = 0
        unmatched_invoice = []
        unmatched_po = []
        
        # Simple matching by description
        for inv_item in invoice_items:
            found = False
            for po_item in po_items:
                if inv_item.get('description') == po_item.get('description'):
                    matched += 1
                    found = True
                    break
            if not found:
                unmatched_invoice.append(inv_item.get('description'))
        
        # Find unmatched PO items
        for po_item in po_items:
            found = False
            for inv_item in invoice_items:
                if po_item.get('description') == inv_item.get('description'):
                    found = True
                    break
            if not found:
                unmatched_po.append(po_item.get('description'))
        
        return {
            'total_invoice_items': len(invoice_items),
            'total_po_items': len(po_items),
            'matched_items': matched,
            'unmatched_invoice_items': unmatched_invoice,
            'unmatched_po_items': unmatched_po
        }


# Create node instance
reconcile_node = ReconcileNode()

