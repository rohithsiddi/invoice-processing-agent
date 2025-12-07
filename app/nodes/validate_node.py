"""
VALIDATE Node - Validate extracted invoice fields
"""
from typing import List, Dict, Any
from datetime import datetime

from app.nodes.base_node import DeterministicNode
from core.models.state import InvoiceState
from core.utils.helpers import parse_date
from core.utils.logging_config import get_logger

logger = get_logger(__name__)


class ValidateNode(DeterministicNode):
    """
    VALIDATE node: Validate extracted invoice fields
    
    Responsibilities:
    - Check required fields are present
    - Validate data formats (dates, amounts)
    - Check for duplicates
    - Business rule validation
    - Populate validation_errors list
    """
    
    def __init__(self):
        super().__init__(name="VALIDATE")
    
    def execute(self, state: InvoiceState) -> InvoiceState:
        """
        Execute VALIDATE logic
        
        Args:
            state: Current workflow state
            
        Returns:
            Updated state with validation_errors and is_valid
        """
        logger.info("Starting invoice validation")
        
        # Validate required fields
        self.validate_required_fields(state, ['invoice_id', 'extracted_data'])
        
        extracted_data = state['extracted_data']
        vendor_info = state.get('vendor_info', {})
        
        # Run all validation checks
        validation_errors = []
        
        validation_errors.extend(self._validate_required_fields(extracted_data))
        validation_errors.extend(self._validate_amounts(extracted_data))
        validation_errors.extend(self._validate_dates(extracted_data))
        validation_errors.extend(self._validate_vendor(extracted_data, vendor_info))
        validation_errors.extend(self._validate_business_rules(extracted_data, vendor_info))
        validation_errors.extend(self._check_duplicates(state))
        
        # Determine if valid
        is_valid = len(validation_errors) == 0
        
        # Update state
        state['validation_errors'] = validation_errors
        state['is_valid'] = is_valid
        state['status'] = 'VALIDATED' if is_valid else 'VALIDATION_FAILED'
        
        if is_valid:
            logger.info("Validation passed - No errors found")
        else:
            logger.warning(f"Validation failed - {len(validation_errors)} errors found")
            for error in validation_errors:
                logger.warning(f"  - {error}")
        
        return state
    
    def _validate_required_fields(self, data: Dict[str, Any]) -> List[str]:
        """Validate that required fields are present"""
        errors = []
        required_fields = [
            'vendor_name',
            'invoice_number',
            'invoice_date',
            'total_amount'
        ]
        
        for field in required_fields:
            if field not in data or data[field] is None or data[field] == '':
                errors.append(f"Missing required field: {field}")
        
        return errors
    
    def _validate_amounts(self, data: Dict[str, Any]) -> List[str]:
        """Validate amount fields"""
        errors = []
        
        # Check total amount
        total_amount = data.get('total_amount')
        if total_amount is not None:
            if not isinstance(total_amount, (int, float)):
                errors.append(f"Invalid total_amount format: {total_amount}")
            elif total_amount <= 0:
                errors.append(f"Total amount must be positive: {total_amount}")
            elif total_amount > 1000000:
                errors.append(f"Total amount exceeds maximum limit: ${total_amount:,.2f}")
        
        # Validate line items sum matches total (if applicable)
        line_items = data.get('line_items', [])
        if line_items and total_amount:
            line_items_total = sum(item.get('amount', 0) for item in line_items)
            subtotal = data.get('subtotal', line_items_total)
            tax_amount = data.get('tax_amount', 0)
            
            expected_total = subtotal + tax_amount
            tolerance = 0.02  # $0.02 tolerance for rounding
            
            if abs(expected_total - total_amount) > tolerance:
                errors.append(
                    f"Total amount mismatch: Expected ${expected_total:.2f} "
                    f"(Subtotal ${subtotal:.2f} + Tax ${tax_amount:.2f}), "
                    f"but got ${total_amount:.2f}"
                )
        
        return errors
    
    def _validate_dates(self, data: Dict[str, Any]) -> List[str]:
        """Validate date fields"""
        errors = []
        
        # Validate invoice date
        invoice_date_str = data.get('invoice_date')
        if invoice_date_str:
            invoice_date = parse_date(invoice_date_str)
            if invoice_date is None:
                errors.append(f"Invalid invoice_date format: {invoice_date_str}")
            else:
                # Check if date is not in the future
                if invoice_date > datetime.now():
                    errors.append(f"Invoice date cannot be in the future: {invoice_date_str}")
                
                # Check if date is not too old (e.g., more than 2 years)
                days_old = (datetime.now() - invoice_date).days
                if days_old > 730:  # 2 years
                    errors.append(f"Invoice date is too old ({days_old} days): {invoice_date_str}")
        
        # Validate due date if present
        due_date_str = data.get('due_date')
        if due_date_str and invoice_date_str:
            due_date = parse_date(due_date_str)
            invoice_date = parse_date(invoice_date_str)
            
            if due_date and invoice_date:
                if due_date < invoice_date:
                    errors.append(
                        f"Due date ({due_date_str}) cannot be before invoice date ({invoice_date_str})"
                    )
        
        return errors
    
    def _validate_vendor(
        self,
        data: Dict[str, Any],
        vendor_info: Dict[str, Any]
    ) -> List[str]:
        """Validate vendor information"""
        errors = []
        
        # Check if vendor is approved
        if vendor_info:
            if not vendor_info.get('is_approved_vendor', False):
                errors.append(f"Vendor is not approved: {data.get('vendor_name')}")
        
        # Validate tax ID format if present
        tax_id = data.get('tax_id')
        if tax_id:
            # Simple US EIN format check: XX-XXXXXXX
            import re
            if not re.match(r'^\d{2}-\d{7}$', tax_id):
                errors.append(f"Invalid tax ID format: {tax_id} (expected XX-XXXXXXX)")
        
        return errors
    
    def _validate_business_rules(
        self,
        data: Dict[str, Any],
        vendor_info: Dict[str, Any]
    ) -> List[str]:
        """Validate business rules"""
        errors = []
        
        total_amount = data.get('total_amount', 0)
        
        # Check credit limit
        if vendor_info:
            credit_limit = vendor_info.get('credit_limit', 0)
            if total_amount > credit_limit:
                errors.append(
                    f"Invoice amount ${total_amount:,.2f} exceeds vendor credit limit "
                    f"${credit_limit:,.2f}"
                )
        
        # Validate line items
        line_items = data.get('line_items', [])
        for i, item in enumerate(line_items, 1):
            # Check required fields in line items
            if 'description' not in item or not item['description']:
                errors.append(f"Line item {i}: Missing description")
            
            if 'quantity' not in item or item['quantity'] <= 0:
                errors.append(f"Line item {i}: Invalid quantity")
            
            if 'unit_price' not in item or item['unit_price'] < 0:
                errors.append(f"Line item {i}: Invalid unit price")
            
            # Validate line item calculation
            if all(k in item for k in ['quantity', 'unit_price', 'amount']):
                expected_amount = item['quantity'] * item['unit_price']
                if abs(expected_amount - item['amount']) > 0.01:
                    errors.append(
                        f"Line item {i}: Amount mismatch - "
                        f"{item['quantity']} x ${item['unit_price']} = ${expected_amount:.2f}, "
                        f"but got ${item['amount']:.2f}"
                    )
        
        return errors
    
    def _check_duplicates(self, state: InvoiceState) -> List[str]:
        """Check for duplicate invoices"""
        errors = []
        
        # In production, this would query the database
        # For now, we'll do a simple check
        from core.models.database import get_session, Invoice
        
        extracted_data = state['extracted_data']
        invoice_number = extracted_data.get('invoice_number')
        vendor_name = extracted_data.get('vendor_name')
        
        if invoice_number and vendor_name:
            try:
                session = get_session()
                # Check if invoice with same number and vendor exists
                existing = session.query(Invoice).filter(
                    Invoice.invoice_number == invoice_number,
                    Invoice.vendor_name == vendor_name,
                    Invoice.invoice_id != state['invoice_id']  # Exclude current invoice
                ).first()
                
                if existing:
                    errors.append(
                        f"Duplicate invoice detected: {invoice_number} from {vendor_name} "
                        f"(existing invoice: {existing.invoice_id})"
                    )
                
                session.close()
            except Exception as e:
                logger.warning(f"Could not check for duplicates: {e}")
        
        return errors


# Create node instance
validate_node = ValidateNode()

