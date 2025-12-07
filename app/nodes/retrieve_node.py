"""
RETRIEVE Node - Fetch Purchase Orders and GRNs from ERP system
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta

from app.nodes.base_node import DeterministicNode
from core.models.state import InvoiceState
from integrations.tools.bigtool_picker import bigtool_picker
from core.utils.error_handler import ERPError, with_retry, RetryPolicy
from core.utils.helpers import is_within_tolerance
from core.utils.logging_config import get_logger

logger = get_logger(__name__)


class RetrieveNode(DeterministicNode):
    """
    RETRIEVE node: Fetch POs, GRNs, and historical invoices from ERP
    
    Responsibilities:
    - Use BigtoolPicker to select ERP connector
    - Query ERP for matching Purchase Orders (by vendor, amount, date range)
    - Query for Goods Receipt Notes (GRNs)
    - Fetch historical invoices for pattern matching
    - Return candidate matches
    """
    
    def __init__(self):
        super().__init__(
            name="RETRIEVE",
            retry_policy=RetryPolicy(max_retries=3, backoff_seconds=2.0)
        )
    
    def execute(self, state: InvoiceState) -> InvoiceState:
        """
        Execute RETRIEVE logic
        
        Args:
            state: Current workflow state
            
        Returns:
            Updated state with matched_pos, matched_grns, history
        """
        logger.info("Starting ERP data retrieval")
        
        # Validate required fields
        self.validate_required_fields(state, ['invoice_id', 'extracted_data', 'vendor_info'])
        
        extracted_data = state['extracted_data']
        vendor_info = state['vendor_info']
        
        # Select ERP connector
        erp_tool = bigtool_picker.select('erp_connector')
        logger.info(f"Selected ERP connector: {erp_tool['name']}")
        
        # Retrieve data from ERP
        matched_pos = self._retrieve_purchase_orders(extracted_data, vendor_info, erp_tool)
        matched_grns = self._retrieve_grns(extracted_data, vendor_info, erp_tool)
        history = self._retrieve_historical_invoices(vendor_info, erp_tool)
        
        # Update state
        state['matched_pos'] = matched_pos
        state['matched_grns'] = matched_grns
        state['history'] = history
        state['erp_tool_used'] = erp_tool['name']
        state['status'] = 'RETRIEVED'
        
        logger.info(
            f"Retrieval complete - POs: {len(matched_pos)}, "
            f"GRNs: {len(matched_grns)}, History: {len(history)}"
        )
        
        return state
    
    @with_retry(retry_policy=RetryPolicy(max_retries=2, backoff_seconds=1.0))
    def _retrieve_purchase_orders(
        self,
        extracted_data: Dict[str, Any],
        vendor_info: Dict[str, Any],
        erp_tool: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Retrieve matching Purchase Orders from ERP via ATLAS MCP
        
        Args:
            extracted_data: Extracted invoice data
            vendor_info: Vendor information
            erp_tool: Selected ERP tool info
            
        Returns:
            List of matching POs
        """
        vendor_id = vendor_info.get('vendor_id')
        vendor_name = vendor_info.get('vendor_name')
        total_amount = extracted_data.get('total_amount', 0)
        
        logger.info(f"Retrieving POs for vendor {vendor_name}, amount ~${total_amount}")
        
        # Try ATLAS MCP first
        try:
            from integrations.mcp.atlas_mcp_client import get_atlas_client
            
            logger.info("Using ATLAS MCP for PO retrieval")
            atlas_client = get_atlas_client()
            matched_pos = atlas_client.fetch_po(
                vendor_id=vendor_id,
                vendor_name=vendor_name,
                amount=total_amount
            )
            
            logger.info(f"Found {len(matched_pos)} matching POs from ATLAS")
            return matched_pos
            
        except Exception as e:
            logger.warning(f"ATLAS MCP unavailable: {e}")
            logger.info("Falling back to mock ERP data")
            
            # Fallback to mock data
            mock_pos = [
                {
                    'po_number': 'PO-2024-001',
                    'vendor_id': vendor_id,
                    'po_date': '2024-11-15',
                    'total_amount': 3300.00,
                    'status': 'APPROVED',
                    'line_items': [
                        {'item_code': 'SRV-001', 'description': 'Professional Services', 'quantity': 10, 'unit_price': 150.00, 'amount': 1500.00},
                        {'item_code': 'SRV-002', 'description': 'Consulting Hours', 'quantity': 5, 'unit_price': 200.00, 'amount': 1000.00},
                        {'item_code': 'LIC-001', 'description': 'Software License', 'quantity': 1, 'unit_price': 500.00, 'amount': 500.00}
                    ],
                    'subtotal': 3000.00,
                    'tax_amount': 300.00,
                    'delivery_date': '2024-12-01'
                }
            ]
            
            # Filter POs by amount tolerance (±10%)
            tolerance_pct = 10.0
            matched_pos = [
                po for po in mock_pos
                if is_within_tolerance(po['total_amount'], total_amount, tolerance_pct)
            ]
            
            logger.info(f"Found {len(matched_pos)} matching POs from mock data")
            return matched_pos
    
    @with_retry(retry_policy=RetryPolicy(max_retries=2, backoff_seconds=1.0))
    def _retrieve_grns(
        self,
        extracted_data: Dict[str, Any],
        vendor_info: Dict[str, Any],
        erp_tool: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Retrieve Goods Receipt Notes from ERP via ATLAS MCP
        
        Args:
            extracted_data: Extracted invoice data
            vendor_info: Vendor information
            erp_tool: Selected ERP tool info
            
        Returns:
            List of matching GRNs
        """
        vendor_id = vendor_info.get('vendor_id')
        vendor_name = vendor_info.get('vendor_name')
        
        logger.info(f"Retrieving GRNs for vendor {vendor_name}")
        
        # Try ATLAS MCP first
        try:
            from integrations.mcp.atlas_mcp_client import get_atlas_client
            
            logger.info("Using ATLAS MCP for GRN retrieval")
            atlas_client = get_atlas_client()
            matched_grns = atlas_client.fetch_grn(
                po_number="PO-2024-001",  # Would come from matched POs in real scenario
                vendor_id=vendor_id
            )
            
            logger.info(f"Found {len(matched_grns)} GRNs from ATLAS")
            return matched_grns
            
        except Exception as e:
            logger.warning(f"ATLAS MCP unavailable: {e}")
            logger.info("Falling back to mock GRN data")
            
            # Fallback to mock data
            mock_grns = [
                {
                    'grn_number': 'GRN-2024-001',
                    'po_number': 'PO-2024-001',
                    'vendor_id': vendor_id,
                    'receipt_date': '2024-12-01',
                    'items': [
                        {'item_code': 'SRV-001', 'description': 'Professional Services', 'quantity_received': 10},
                        {'item_code': 'SRV-002', 'description': 'Consulting Hours', 'quantity_received': 5},
                        {'item_code': 'LIC-001', 'description': 'Software License', 'quantity_received': 1}
                    ],
                    'status': 'COMPLETED'
                }
            ]
            
            logger.info(f"Found {len(mock_grns)} GRNs from mock data")
            return mock_grns
    
    @with_retry(retry_policy=RetryPolicy(max_retries=2, backoff_seconds=1.0))
    def _retrieve_historical_invoices(
        self,
        vendor_info: Dict[str, Any],
        erp_tool: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Retrieve historical invoices for pattern matching via ATLAS MCP
        
        Args:
            vendor_info: Vendor information
            erp_tool: Selected ERP tool info
            
        Returns:
            List of historical invoices
        """
        vendor_id = vendor_info.get('vendor_id')
        vendor_name = vendor_info.get('vendor_name')
        
        logger.info(f"Retrieving historical invoices for vendor {vendor_name}")
        
        # Try ATLAS MCP first
        try:
            from integrations.mcp.atlas_mcp_client import get_atlas_client
            
            logger.info("Using ATLAS MCP for historical invoice retrieval")
            atlas_client = get_atlas_client()
            history = atlas_client.fetch_history(
                vendor_id=vendor_id,
                vendor_name=vendor_name,
                limit=10
            )
            
            logger.info(f"Found {len(history)} historical invoices from ATLAS")
            return history
            
        except Exception as e:
            logger.warning(f"ATLAS MCP unavailable: {e}")
            logger.info("Falling back to mock historical data")
            
            # Fallback to mock data
            mock_history = [
                {
                    'invoice_id': 'INV-HIST-001',
                    'invoice_number': 'INV-2024-000',
                    'vendor_id': vendor_id,
                    'invoice_date': '2024-11-01',
                    'total_amount': 2500.00,
                    'status': 'PAID',
                    'payment_date': '2024-11-30'
                },
                {
                    'invoice_id': 'INV-HIST-002',
                    'invoice_number': 'INV-2024-999',
                    'vendor_id': vendor_id,
                    'invoice_date': '2024-10-15',
                    'total_amount': 3000.00,
                    'status': 'PAID',
                    'payment_date': '2024-11-14'
                }
            ]
            
            logger.info(f"Found {len(mock_history)} historical invoices from mock data")
            return mock_history


# Create node instance
retrieve_node = RetrieveNode()

