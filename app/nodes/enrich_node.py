"""
ENRICH Node - Enrich vendor information from external sources
"""
from typing import Dict, Any

from app.nodes.base_node import DeterministicNode
from core.models.state import InvoiceState
from integrations.tools.bigtool_picker import bigtool_picker
from core.utils.error_handler import with_retry, RetryPolicy
from core.utils.logging_config import get_logger
from integrations.mcp.common_mcp_client import common_mcp_client
from integrations.mcp.atlas_mcp_client import get_atlas_client

logger = get_logger(__name__)


class EnrichNode(DeterministicNode):
    """
    ENRICH node: Enrich vendor information from external sources
    
    Responsibilities:
    - Use BigtoolPicker to select enrichment tool
    - Fetch vendor details from database or external APIs
    - Add tax_id, address, contact info, payment details
    - Update vendor_info in state
    """
    
    def __init__(self):
        super().__init__(
            name="ENRICH",
            retry_policy=RetryPolicy(max_retries=2, backoff_seconds=1.0)
        )
    
    def execute(self, state: InvoiceState) -> InvoiceState:
        """
        Execute ENRICH logic
        
        Args:
            state: Current workflow state
            
        Returns:
            Updated state with vendor_info
        """
        logger.info("Starting vendor enrichment")
        
        # Validate required fields
        self.validate_required_fields(state, ['invoice_id', 'extracted_data'])
        
        extracted_data = state['extracted_data']
        vendor_name = extracted_data.get('vendor_name')
        
        if not vendor_name:
            logger.warning("No vendor name found in extracted data")
            state['vendor_info'] = {}
            state['status'] = 'ENRICHED'
            return state
        
        # Select enrichment tool
        # First try internal vendor database, then external APIs
        enrichment_tool = bigtool_picker.select(
            'enrichment',
            context={'use_case': 'internal_vendors'}
        )
        
        logger.info(f"Selected enrichment tool: {enrichment_tool['name']}")
        
        # Normalize vendor name using COMMON MCP
        normalized_vendor = common_mcp_client.normalize_vendor(vendor_name)
        
        # Enrich vendor using ATLAS MCP
        atlas = get_atlas_client()
        vendor_info = atlas.enrich_vendor(normalized_vendor)
        
        # Update state
        state['vendor_info'] = vendor_info
        state['enrichment_tool_used'] = enrichment_tool['name']
        state['status'] = 'ENRICHED'
        
        logger.info(
            f"Enrichment complete - Vendor ID: {vendor_info.get('vendor_id')}, "
            f"Tax ID: {vendor_info.get('tax_id')}"
        )
        
        return state
    
    @with_retry(retry_policy=RetryPolicy(max_retries=2, backoff_seconds=1.0))
    def _enrich_vendor(
        self,
        vendor_name: str,
        extracted_data: Dict[str, Any],
        enrichment_tool: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Enrich vendor information using selected tool
        
        Args:
            vendor_name: Vendor name from invoice
            extracted_data: Extracted invoice data
            enrichment_tool: Selected enrichment tool info
            
        Returns:
            Enriched vendor information
        """
        tool_name = enrichment_tool['name']
        
        # Mock enrichment implementation
        # In production, this would query databases or call external APIs
        logger.info(f"Enriching vendor '{vendor_name}' using {tool_name}")
        
        # Check if we have tax_id from extracted data
        tax_id = extracted_data.get('tax_id')
        
        # Mock vendor database lookup
        vendor_info = {
            'vendor_id': self._generate_vendor_id(vendor_name),
            'vendor_name': vendor_name,
            'tax_id': tax_id or self._mock_tax_id(vendor_name),
            'address': self._mock_address(vendor_name),
            'contact_email': self._mock_email(vendor_name),
            'contact_phone': self._mock_phone(),
            'payment_method': 'ACH',
            'payment_terms_default': 'Net 30',
            'vendor_category': self._categorize_vendor(vendor_name),
            'is_approved_vendor': True,
            'credit_limit': 50000.00,
            'enrichment_source': tool_name
        }
        
        return vendor_info
    
    def _generate_vendor_id(self, vendor_name: str) -> str:
        """Generate vendor ID from name"""
        # Simple hash-based ID generation
        import hashlib
        hash_obj = hashlib.md5(vendor_name.encode())
        return f"VND-{hash_obj.hexdigest()[:8].upper()}"
    
    def _mock_tax_id(self, vendor_name: str) -> str:
        """Generate mock tax ID"""
        # In production, this would come from database or API
        return f"12-{hash(vendor_name) % 10000000:07d}"
    
    def _mock_address(self, vendor_name: str) -> str:
        """Generate mock address"""
        return f"123 Business St, Suite {hash(vendor_name) % 1000}, City, State 12345"
    
    def _mock_email(self, vendor_name: str) -> str:
        """Generate mock email"""
        clean_name = vendor_name.lower().replace(' ', '').replace('&', 'and')[:20]
        return f"billing@{clean_name}.com"
    
    def _mock_phone(self) -> str:
        """Generate mock phone"""
        return "+1-555-0100"
    
    def _categorize_vendor(self, vendor_name: str) -> str:
        """Categorize vendor based on name"""
        name_lower = vendor_name.lower()
        
        if any(word in name_lower for word in ['tech', 'software', 'digital', 'it']):
            return 'Technology'
        elif any(word in name_lower for word in ['consult', 'advisory', 'services']):
            return 'Professional Services'
        elif any(word in name_lower for word in ['supply', 'materials', 'equipment']):
            return 'Supplies'
        else:
            return 'General'


# Create node instance
enrich_node = EnrichNode()

