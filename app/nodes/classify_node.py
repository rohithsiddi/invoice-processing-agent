"""
CLASSIFY Node - Classify invoice type using LLM
"""
from typing import Dict, Any

from app.nodes.base_node import NonDeterministicNode
from core.models.state import InvoiceState
from core.utils.logging_config import get_logger

logger = get_logger(__name__)


class ClassifyNode(NonDeterministicNode):
    """
    CLASSIFY node: Determine invoice type using LLM
    
    Responsibilities:
    - Analyze extracted data
    - Classify invoice type (standard, credit_note, debit_note, proforma, etc.)
    - Identify special characteristics
    """
    
    def __init__(self):
        super().__init__(name="CLASSIFY")
    
    def execute(self, state: InvoiceState) -> InvoiceState:
        """
        Execute CLASSIFY logic
        
        Args:
            state: Current workflow state
            
        Returns:
            Updated state with invoice_type
        """
        logger.info("Starting invoice classification")
        
        # Validate required fields
        self.validate_required_fields(state, ['invoice_id', 'extracted_data'])
        
        extracted_data = state['extracted_data']
        
        # Classify invoice type
        invoice_type, characteristics = self._classify_invoice(extracted_data)
        
        # Update state
        state['invoice_type'] = invoice_type
        state['invoice_characteristics'] = characteristics
        state['status'] = 'CLASSIFIED'
        
        logger.info(f"Classification complete - Type: {invoice_type}")
        
        return state
    
    def _classify_invoice(self, data: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        """
        Classify invoice based on extracted data
        
        Args:
            data: Extracted invoice data
            
        Returns:
            Tuple of (invoice_type, characteristics)
        """
        # In production, this would use an LLM (OpenAI, Claude, etc.)
        # For now, we'll use rule-based classification
        
        invoice_number = data.get('invoice_number', '').upper()
        total_amount = data.get('total_amount', 0)
        line_items = data.get('line_items', [])
        
        characteristics = {
            'has_line_items': len(line_items) > 0,
            'item_count': len(line_items),
            'has_tax': 'tax_amount' in data,
            'has_payment_terms': 'payment_terms' in data
        }
        
        # Classification logic
        if 'CREDIT' in invoice_number or total_amount < 0:
            invoice_type = 'credit_note'
            characteristics['reason'] = 'Credit note detected from invoice number or negative amount'
        
        elif 'DEBIT' in invoice_number:
            invoice_type = 'debit_note'
            characteristics['reason'] = 'Debit note detected from invoice number'
        
        elif 'PROFORMA' in invoice_number or 'QUOTE' in invoice_number:
            invoice_type = 'proforma'
            characteristics['reason'] = 'Proforma/quote invoice detected'
        
        elif len(line_items) == 0:
            invoice_type = 'summary'
            characteristics['reason'] = 'No line items - summary invoice'
        
        else:
            invoice_type = 'standard'
            characteristics['reason'] = 'Standard invoice with line items'
        
        logger.info(f"Classified as: {invoice_type} - {characteristics['reason']}")
        
        return invoice_type, characteristics


# Create node instance
classify_node = ClassifyNode()

