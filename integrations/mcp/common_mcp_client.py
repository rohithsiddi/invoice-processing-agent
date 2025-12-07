"""
COMMON MCP Client - Internal Processing Tools

This MCP client provides internal processing capabilities that don't require
external data sources. It centralizes common utilities used across the workflow.

Tools provided:
- parse_invoice_data: Extract structured data from OCR text
- normalize_vendor: Clean and standardize vendor names
- compute_match_score: Calculate invoice-PO matching score
- validate_schema: Validate invoice data structure
- build_accounting_entries: Create GL entries for reconciliation
"""

import re
from typing import Dict, Any, List
from datetime import datetime
from core.utils.logging_config import get_logger

logger = get_logger(__name__)


class CommonMCPClient:
    """
    COMMON MCP Client for internal processing tools
    
    This simulates a local MCP server that provides common utilities
    for invoice processing without requiring external data sources.
    """
    
    def __init__(self):
        logger.info("Initializing COMMON MCP Client")
        logger.info("Mode: LOCAL (internal processing tools)")
    
    def parse_invoice_data(self, text: str) -> Dict[str, Any]:
        """
        Parse invoice data from OCR text
        
        COMMON MCP Tool: parse_invoice_data
        
        Args:
            text: Raw OCR text
            
        Returns:
            Structured invoice data
        """
        logger.info("=" * 60)
        logger.info("COMMON MCP - Parsing Invoice Data")
        logger.info("=" * 60)
        
        data = {}
        
        # Extract vendor name
        vendor_patterns = [
            r'Vendor[:\s]+([A-Za-z\s&.,]+?)(?:\n|$)',  # Stop at newline
            r'From[:\s]+([A-Za-z\s&.,]+?)(?:\n|$)',
            r'Bill\s+To[:\s]+([A-Za-z\s&.,]+?)(?:\n|$)'
        ]
        
        for pattern in vendor_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                data['vendor_name'] = match.group(1).strip()
                break
        
        # Extract invoice number
        inv_num_match = re.search(r'Invoice\s+Number[:\s]+([A-Z0-9-]+)', text, re.IGNORECASE)
        if inv_num_match:
            data['invoice_number'] = inv_num_match.group(1).strip()
        
        # Extract dates
        date_match = re.search(r'Invoice\s+Date[:\s]+([0-9]{4}-[0-9]{2}-[0-9]{2})', text, re.IGNORECASE)
        if date_match:
            data['invoice_date'] = date_match.group(1).strip()
        
        due_match = re.search(r'Due\s+Date[:\s]+([0-9]{4}-[0-9]{2}-[0-9]{2})', text, re.IGNORECASE)
        if due_match:
            data['due_date'] = due_match.group(1).strip()
        
        # Extract total
        total_match = re.search(r'Total[:\s]+\$([0-9,]+\.?\d{0,2})', text, re.IGNORECASE)
        if total_match:
            data['total_amount'] = float(total_match.group(1).replace(',', ''))
        
        # Extract subtotal
        subtotal_match = re.search(r'Subtotal[:\s]+\$([0-9,]+\.?\d{0,2})', text, re.IGNORECASE)
        if subtotal_match:
            data['subtotal'] = float(subtotal_match.group(1).replace(',', ''))
        
        # Extract tax
        tax_match = re.search(r'Tax[:\s]+\$([0-9,]+\.?\d{0,2})', text, re.IGNORECASE)
        if tax_match:
            data['tax_amount'] = float(tax_match.group(1).replace(',', ''))
        
        logger.info(f"Parsed fields: {list(data.keys())}")
        logger.info("=" * 60)
        
        return data
    
    def normalize_vendor(self, vendor_name: str) -> str:
        """
        Normalize vendor name
        
        COMMON MCP Tool: normalize_vendor
        
        Args:
            vendor_name: Raw vendor name
            
        Returns:
            Normalized vendor name
        """
        if not vendor_name:
            return ""
        
        # Remove extra whitespace
        normalized = ' '.join(vendor_name.split())
        
        # Common abbreviations (preserve case)
        replacements = {
            'Corp.': 'Corporation',
            'Inc.': 'Incorporated',
            'Ltd.': 'Limited',
            'LLC': 'LLC'
        }
        
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        
        logger.info(f"Normalized vendor: '{vendor_name}' → '{normalized}'")
        return normalized
    
    def compute_match_score(
        self,
        invoice_data: Dict[str, Any],
        po_data: Dict[str, Any],
        invoice_items: List[Dict],
        po_items: List[Dict]
    ) -> Dict[str, Any]:
        """
        Compute 2-way match score between invoice and PO
        
        COMMON MCP Tool: compute_match_score
        
        Args:
            invoice_data: Invoice data
            po_data: PO data
            invoice_items: Invoice line items
            po_items: PO line items
            
        Returns:
            Match result with score and evidence
        """
        logger.info("=" * 60)
        logger.info("COMMON MCP - Computing Match Score")
        logger.info("=" * 60)
        
        score = 0.0
        weights = {'vendor': 0.3, 'amount': 0.4, 'items': 0.3}
        evidence = {}
        
        # Vendor match
        invoice_vendor = invoice_data.get('vendor_name', '').upper()
        po_vendor = po_data.get('vendor_name', '').upper()
        vendor_match = invoice_vendor == po_vendor
        if vendor_match:
            score += weights['vendor']
        evidence['vendor_match'] = vendor_match
        
        # Amount match (within 5% tolerance)
        invoice_amount = invoice_data.get('total_amount', 0)
        po_amount = po_data.get('total_amount', 0)
        
        amount_diff = abs(invoice_amount - po_amount)
        if po_amount > 0:
            diff_pct = amount_diff / po_amount * 100
            amount_match = diff_pct <= 5.0
            if amount_match:
                score += weights['amount']
            evidence['amount_match'] = amount_match
            evidence['amount_diff'] = amount_diff
            evidence['amount_diff_pct'] = diff_pct
        
        # Line items match
        matched_items = 0
        for inv_item in invoice_items:
            for po_item in po_items:
                if inv_item.get('description', '').upper() == po_item.get('description', '').upper():
                    matched_items += 1
                    break
        
        if len(po_items) > 0:
            item_match_pct = matched_items / len(po_items)
            score += weights['items'] * item_match_pct
            evidence['items_matched'] = matched_items
            evidence['items_total'] = len(po_items)
            evidence['items_match'] = matched_items == len(po_items)
        
        logger.info(f"Match Score: {score:.2f}")
        logger.info(f"Vendor Match: {vendor_match}")
        logger.info(f"Amount Match: {evidence.get('amount_match', False)}")
        logger.info(f"Items Matched: {matched_items}/{len(po_items)}")
        logger.info("=" * 60)
        
        return {
            'match_score': score,
            'match_result': 'MATCHED' if score >= 0.85 else 'FAILED',
            'evidence': evidence
        }
    
    def validate_schema(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate invoice data schema
        
        COMMON MCP Tool: validate_schema
        
        Args:
            data: Invoice data to validate
            
        Returns:
            Validation result with errors
        """
        logger.info("COMMON MCP - Validating Schema")
        
        errors = []
        required_fields = ['vendor_name', 'invoice_number', 'total_amount']
        
        for field in required_fields:
            if not data.get(field):
                errors.append(f"Missing required field: {field}")
        
        # Validate amount
        if data.get('total_amount') and data['total_amount'] <= 0:
            errors.append("Total amount must be positive")
        
        is_valid = len(errors) == 0
        logger.info(f"Validation: {'PASSED' if is_valid else 'FAILED'} ({len(errors)} errors)")
        
        return {
            'is_valid': is_valid,
            'errors': errors
        }
    
    def build_accounting_entries(
        self,
        invoice_data: Dict[str, Any],
        po_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Build accounting entries for reconciliation
        
        COMMON MCP Tool: build_accounting_entries
        
        Args:
            invoice_data: Invoice data
            po_data: PO data
            
        Returns:
            List of GL entries
        """
        logger.info("COMMON MCP - Building Accounting Entries")
        
        amount = invoice_data.get('total_amount', 0)
        
        entries = [
            {
                'account': '6000',  # Expense
                'description': 'Invoice Expense',
                'debit': amount,
                'credit': 0,
                'timestamp': datetime.utcnow().isoformat()
            },
            {
                'account': '2000',  # Accounts Payable
                'description': 'Accounts Payable',
                'debit': 0,
                'credit': amount,
                'timestamp': datetime.utcnow().isoformat()
            }
        ]
        
        logger.info(f"Created {len(entries)} accounting entries")
        return entries


# Create singleton instance
common_mcp_client = CommonMCPClient()
