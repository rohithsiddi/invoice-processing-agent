"""
INGEST Node - Handles invoice file upload and initial processing
"""
import os
import shutil
from pathlib import Path
from datetime import datetime

from app.nodes.base_node import DeterministicNode
from core.models.state import InvoiceState
from core.utils.helpers import generate_invoice_id, sanitize_filename
from core.utils.logging_config import get_logger

logger = get_logger(__name__)


class IngestNode(DeterministicNode):
    """
    INGEST node: Accept uploaded invoice file and initialize workflow state
    
    Responsibilities:
    - Accept file upload (PDF, PNG, JPG)
    - Generate unique invoice_id
    - Store file in designated location
    - Initialize state with file metadata
    """
    
    def __init__(self, upload_dir: str = "./data/uploads"):
        super().__init__(name="INGEST")
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
    
    def execute(self, state: InvoiceState) -> InvoiceState:
        """
        Execute INGEST logic
        
        Args:
            state: Current workflow state (should contain 'file_path' for source file)
            
        Returns:
            Updated state with invoice_id and stored file_path
        """
        logger.info("Starting invoice ingestion")
        
        # Get source file path from state
        source_file = state.get('file_path')
        if not source_file:
            raise ValueError("No file_path provided in state")
        
        source_path = Path(source_file)
        
        # Validate file exists
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_file}")
        
        # Validate file type
        allowed_extensions = {'.pdf', '.png', '.jpg', '.jpeg'}
        file_extension = source_path.suffix.lower()
        
        if file_extension not in allowed_extensions:
            raise ValueError(
                f"Unsupported file type: {file_extension}. "
                f"Allowed types: {allowed_extensions}"
            )
        
        # Generate invoice ID if not already present
        invoice_id = state.get('invoice_id')
        if not invoice_id:
            invoice_id = generate_invoice_id()
            logger.info(f"Generated invoice ID: {invoice_id}")
        
        # Create sanitized filename
        sanitized_name = sanitize_filename(source_path.stem)
        new_filename = f"{invoice_id}_{sanitized_name}{file_extension}"
        destination_path = self.upload_dir / new_filename
        
        # Copy file to upload directory
        shutil.copy2(source_path, destination_path)
        logger.info(f"File copied to: {destination_path}")
        
        # Get file metadata
        file_size = destination_path.stat().st_size
        
        # Update state
        state['invoice_id'] = invoice_id
        state['file_path'] = str(destination_path)
        state['file_type'] = file_extension.lstrip('.')
        state['file_size'] = file_size
        state['status'] = 'INGESTED'
        state['ingested_at'] = datetime.utcnow().isoformat()
        
        logger.info(
            f"Ingestion complete - Invoice: {invoice_id}, "
            f"Type: {file_extension}, Size: {file_size} bytes"
        )
        
        return state


# Create node instance
ingest_node = IngestNode()

