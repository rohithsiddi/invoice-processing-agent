"""
MATCH_TWO_WAY Node - Perform 2-way matching between invoice and PO
"""
from typing import Dict, Any, List
from core.config.config import config
from app.nodes.base_node import DeterministicNode
from core.models.state import InvoiceState
from core.utils.helpers import is_within_tolerance
from core.utils.logging_config import get_logger
from integrations.mcp.common_mcp_client import common_mcp_client

logger = get_logger(__name__)


class MatchTwoWayNode(DeterministicNode):
    """
    MATCH_TWO_WAY node: Compute 2-way match score between invoice and PO
    
    Responsibilities:
    - Compare invoice line items with PO line items
    - Calculate match score based on vendor, amount, items
    - If match_score >= threshold: set match_result='MATCHED'
    - Else: set match_result='FAILED'
    - Include tolerance analysis
    """
    
    def __init__(self):
        super().__init__(name="MATCH_TWO_WAY")
        self.match_threshold = config.MATCH_THRESHOLD
        self.tolerance_pct = config.TOLERANCE_PERCENTAGE
    
    def execute(self, state: InvoiceState) -> InvoiceState:
        """
        Execute MATCH_TWO_WAY logic
        
        Args:
            state: Current workflow state
            
        Returns:
            Updated state with match_score, match_result, tolerance_pct, match_evidence
        """
        logger.info("Starting 2-way matching")
        
        # Validate required fields
        self.validate_required_fields(state, ['invoice_id', 'extracted_data', 'matched_pos'])
        
        extracted_data = state['extracted_data']
        matched_pos = state['matched_pos']
        
        if not matched_pos:
            logger.warning("No POs found for matching")
            state['match_score'] = 0.0
            state['match_result'] = 'FAILED'
            state['match_evidence'] = {'reason': 'No matching POs found'}
            state['status'] = 'MATCH_FAILED'
            return state
        
        # Perform matching with best PO
        best_match = None
        best_score = 0.0
        best_evidence = {}
        
        for po in matched_pos:
            score, evidence = self._calculate_match_score(extracted_data, po)
            if score > best_score:
                best_score = score
                best_match = po
                best_evidence = evidence
        
        # Determine match result
        if best_score >= self.match_threshold:
            match_result = 'MATCHED'
            status = 'MATCHED'
            logger.info(f"Match successful - Score: {best_score:.2f}, PO: {best_match['po_number']}")
        else:
            match_result = 'FAILED'
            status = 'MATCH_FAILED'
            logger.warning(f"Match failed - Score: {best_score:.2f} < Threshold: {self.match_threshold}")
        
        # Update state
        state['match_score'] = best_score
        state['match_result'] = match_result
        state['tolerance_pct'] = self.tolerance_pct
        state['match_evidence'] = best_evidence
        state['matched_po'] = best_match
        state['status'] = status
        
        return state
    
    
    def _calculate_match_score(
        self,
        invoice_data: Dict[str, Any],
        po: Dict[str, Any]
    ) -> tuple[float, Dict[str, Any]]:
        """
        Calculate match score between invoice and PO using COMMON MCP
        
        Args:
            invoice_data: Extracted invoice data
            po: Purchase order data
            
        Returns:
            Tuple of (match_score, evidence_dict)
        """
        # Use COMMON MCP for match score calculation
        invoice_items = invoice_data.get('line_items', [])
        po_items = po.get('line_items', [])
        
        # Call COMMON MCP client
        result = common_mcp_client.compute_match_score(
            invoice_data, po, invoice_items, po_items
        )
        
        match_score = result['match_score']
        evidence = result['evidence']
        
        # Add PO number to evidence
        evidence['po_number'] = po['po_number']
        
        # Log result
        items_matched = evidence.get('items_matched', '0/0')
        logger.info(
            f"Match score for PO {po['po_number']}: {match_score:.2f} "
            f"(Vendor: {evidence.get('vendor_match')}, Amount: {evidence.get('amount_match')}, "
            f"Items: {items_matched})"
        )
        
        return match_score, evidence
    
    def _match_vendor(self, invoice_data: Dict[str, Any], po: Dict[str, Any]) -> bool:
        """Check if vendor matches"""
        # In production, would compare vendor IDs
        # For now, assume vendor matches if PO was retrieved for this vendor
        return True
    
    def _match_amount(self, invoice_data: Dict[str, Any], po: Dict[str, Any]) -> tuple[float, float]:
        """
        Match invoice amount with PO amount
        
        Returns:
            Tuple of (score, difference)
        """
        invoice_amount = invoice_data.get('total_amount', 0)
        po_amount = po.get('total_amount', 0)
        
        diff = invoice_amount - po_amount
        
        # Check if within tolerance
        if is_within_tolerance(invoice_amount, po_amount, self.tolerance_pct):
            return 1.0, diff
        else:
            # Partial score based on how far off
            diff_pct = abs(diff) / po_amount * 100 if po_amount > 0 else 100
            if diff_pct <= self.tolerance_pct * 2:  # Within 2x tolerance
                return 0.5, diff
            else:
                return 0.0, diff
    
    def _match_line_items(
        self,
        invoice_data: Dict[str, Any],
        po: Dict[str, Any]
    ) -> tuple[float, int, int]:
        """
        Match invoice line items with PO line items
        
        Returns:
            Tuple of (score, matched_count, total_count)
        """
        invoice_items = invoice_data.get('line_items', [])
        po_items = po.get('line_items', [])
        
        if not invoice_items or not po_items:
            return 0.0, 0, max(len(invoice_items), len(po_items))
        
        matched_count = 0
        total_items = len(invoice_items)
        
        # Try to match each invoice item with PO items
        for inv_item in invoice_items:
            inv_desc = inv_item.get('description', '').lower()
            inv_qty = inv_item.get('quantity', 0)
            inv_price = inv_item.get('unit_price', 0)
            
            for po_item in po_items:
                po_desc = po_item.get('description', '').lower()
                po_qty = po_item.get('quantity', 0)
                po_price = po_item.get('unit_price', 0)
                
                # Check if descriptions match (fuzzy)
                desc_match = inv_desc in po_desc or po_desc in inv_desc
                
                # Check if quantities match (exact or within tolerance)
                qty_match = inv_qty == po_qty or is_within_tolerance(inv_qty, po_qty, 5.0)
                
                # Check if prices match (within tolerance)
                price_match = is_within_tolerance(inv_price, po_price, self.tolerance_pct)
                
                if desc_match and qty_match and price_match:
                    matched_count += 1
                    break
        
        # Calculate score
        match_ratio = matched_count / total_items if total_items > 0 else 0
        
        return match_ratio, matched_count, total_items
    
    def _match_dates(self, invoice_data: Dict[str, Any], po: Dict[str, Any]) -> float:
        """
        Check date proximity between invoice and PO
        
        Returns:
            Score based on date proximity
        """
        from core.utils.helpers import parse_date
        
        invoice_date_str = invoice_data.get('invoice_date')
        po_date_str = po.get('po_date')
        
        if not invoice_date_str or not po_date_str:
            return 0.5  # Neutral score if dates missing
        
        invoice_date = parse_date(invoice_date_str)
        po_date = parse_date(po_date_str)
        
        if not invoice_date or not po_date:
            return 0.5
        
        # Invoice should be after PO
        if invoice_date < po_date:
            return 0.0
        
        # Check days difference
        days_diff = (invoice_date - po_date).days
        
        if days_diff <= 30:  # Within 30 days
            return 1.0
        elif days_diff <= 60:  # Within 60 days
            return 0.7
        elif days_diff <= 90:  # Within 90 days
            return 0.5
        else:
            return 0.3


# Create node instance
match_two_way_node = MatchTwoWayNode()

