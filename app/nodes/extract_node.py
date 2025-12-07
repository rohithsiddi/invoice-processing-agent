"""
EXTRACT Node - OCR text extraction from invoice files
"""
from pathlib import Path
from typing import Dict, Any
import re

from app.nodes.base_node import DeterministicNode
from core.models.state import InvoiceState
from integrations.tools.bigtool_picker import bigtool_picker
from core.utils.error_handler import with_retry, RetryPolicy
from core.utils.logging_config import get_logger
from integrations.mcp.common_mcp_client import common_mcp_client

logger = get_logger(__name__)


class ExtractNode(DeterministicNode):
    """
    EXTRACT node: Extract invoice data from uploaded file using OCR
    
    Responsibilities:
    - Use LLM Bigtool Picker to select best OCR tool (Tesseract vs EasyOCR)
    - Perform OCR on invoice image/PDF
    - Parse extracted text into structured data using COMMON MCP
    - Update state with extracted_data
    """
    
    def __init__(self):
        super().__init__(
            name="EXTRACT",
            retry_policy=RetryPolicy(max_retries=2, backoff_seconds=1.0)
        )
    
    def execute(self, state: InvoiceState) -> InvoiceState:
        """
        Execute EXTRACT logic
        
        Args:
            state: Current workflow state
            
        Returns:
            Updated state with extracted_data
        """
        logger.info("Starting OCR extraction with LLM Bigtool Picker")
        
        # Validate required fields
        self.validate_required_fields(state, ['invoice_id', 'file_path'])
        
        file_path = state['file_path']
        file_type = state.get('file_type', 'unknown')
        
        # Build context for OCR tool selection
        context = {
            'file_type': file_type,
            'file_size': state.get('file_size', 0),
            'quality_hint': 'high',  # Assume high quality by default
            'has_handwriting': False,  # Assume no handwriting
            'language': 'en'
        }
        
        # Use LLM Bigtool Picker to select best OCR tool
        selected_tool = bigtool_picker.select_ocr_tool(context)
        tool_info = bigtool_picker.get_tool_info(selected_tool, 'ocr')
        
        logger.info(f"LLM Selected OCR Tool: {tool_info['name']}")
        
        # Perform OCR extraction with selected tool
        extracted_text, confidence = self._perform_ocr(file_path, selected_tool, tool_info)
        
        # Parse extracted text into structured data
        extracted_data = self._parse_invoice_data(extracted_text)
        
        # Update state
        state['extracted_text'] = extracted_text
        state['extracted_data'] = extracted_data
        state['confidence_score'] = confidence
        state['ocr_tool_used'] = tool_info['name']
        state['status'] = 'EXTRACTED'
        
        logger.info(
            f"Extraction complete - Vendor: {extracted_data.get('vendor_name')}, "
            f"Amount: {extracted_data.get('total_amount')}, Confidence: {confidence}"
        )
        
        return state
    
    @with_retry(retry_policy=RetryPolicy(max_retries=2, backoff_seconds=1.0))
    def _perform_ocr(self, file_path: str, selected_tool: str, tool_info: Dict[str, Any]) -> tuple[str, float]:
        """
        Perform OCR extraction using the LLM-selected tool
        
        Args:
            file_path: Path to invoice file (PDF or image)
            selected_tool: Tool selected by LLM ('tesseract' or 'easyocr')
            tool_info: Tool information dictionary
            
        Returns:
            Tuple of (extracted_text, confidence_score)
        """
        logger.info("=" * 60)
        logger.info("OCR TOOL SELECTION - LLM BigTool Picker")
        logger.info("=" * 60)
        logger.info(f"Selected OCR Tool: {selected_tool}")
        logger.info(f"Tool Info: {tool_info}")
        logger.info(f"File Path: {file_path}")
        logger.info("=" * 60)
        
        file_ext = Path(file_path).suffix.lower()
        
        # Route to appropriate OCR tool
        if selected_tool == 'easyocr':
            return self._perform_easyocr(file_path, file_ext)
        else:  # Default to tesseract
            return self._perform_tesseract_ocr(file_path, file_ext)
    
    def _perform_tesseract_ocr(self, file_path: str, file_ext: str) -> tuple[str, float]:
        """Perform OCR using Tesseract"""
        try:
            import pytesseract
            from PIL import Image
            
            if file_ext in ['.jpg', '.jpeg', '.png', '.tiff', '.bmp']:
                logger.info(f"Tesseract: Processing image file: {file_ext}")
                
                image = Image.open(file_path)
                tesseract_config = r'--psm 6'
                
                ocr_data = pytesseract.image_to_data(image, config=tesseract_config, output_type=pytesseract.Output.DICT)
                extracted_text = pytesseract.image_to_string(image, config=tesseract_config)
                
                confidences = [int(conf) for conf in ocr_data['conf'] if conf != '-1']
                if confidences:
                    avg_confidence = sum(confidences) / len(confidences)
                    confidence = avg_confidence / 100
                else:
                    confidence = 0.5
                
                logger.info(f"Tesseract: Extracted {len(extracted_text)} characters, confidence: {confidence:.2f}")
                return extracted_text, confidence
                
            elif file_ext == '.pdf':
                from pdf2image import convert_from_path
                
                images = convert_from_path(file_path, dpi=300)
                extracted_text = ""
                total_confidence = 0
                
                for page_num, image in enumerate(images, 1):
                    ocr_data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
                    page_text = pytesseract.image_to_string(image)
                    extracted_text += page_text + "\n"
                    
                    confidences = [int(conf) for conf in ocr_data['conf'] if conf != '-1']
                    if confidences:
                        page_confidence = sum(confidences) / len(confidences)
                        total_confidence += page_confidence
                
                confidence = (total_confidence / len(images)) / 100 if len(images) > 0 else 0.0
                logger.info(f"Tesseract: Processed {len(images)} pages, confidence: {confidence:.2f}")
                return extracted_text, confidence
            
            else:
                raise ValueError(f"Unsupported file type: {file_ext}")
                
        except Exception as e:
            logger.error(f"Tesseract OCR failed: {e}")
            raise OCRError(f"Tesseract failed: {e}")
    
    def _perform_easyocr(self, file_path: str, file_ext: str) -> tuple[str, float]:
        """Perform OCR using EasyOCR"""
        try:
            import easyocr
            from PIL import Image
            import numpy as np
            
            logger.info("EasyOCR: Initializing reader...")
            reader = easyocr.Reader(['en'], gpu=False)  # CPU mode for compatibility
            
            if file_ext in ['.jpg', '.jpeg', '.png', '.tiff', '.bmp']:
                logger.info(f"EasyOCR: Processing image file: {file_ext}")
                
                # EasyOCR can read directly from file path
                results = reader.readtext(file_path, detail=1)
                
                # Extract text and confidence
                extracted_text = "\n".join([text for (bbox, text, conf) in results])
                
                # Calculate average confidence
                if results:
                    avg_confidence = sum([conf for (bbox, text, conf) in results]) / len(results)
                else:
                    avg_confidence = 0.5
                
                logger.info(f"EasyOCR: Extracted {len(extracted_text)} characters, confidence: {avg_confidence:.2f}")
                return extracted_text, avg_confidence
                
            elif file_ext == '.pdf':
                from pdf2image import convert_from_path
                
                logger.info("EasyOCR: Converting PDF to images...")
                images = convert_from_path(file_path, dpi=300)
                
                extracted_text = ""
                total_confidence = 0
                
                for page_num, image in enumerate(images, 1):
                    logger.info(f"EasyOCR: Processing page {page_num}...")
                    
                    # Convert PIL Image to numpy array for EasyOCR
                    img_array = np.array(image)
                    results = reader.readtext(img_array, detail=1)
                    
                    page_text = "\n".join([text for (bbox, text, conf) in results])
                    extracted_text += page_text + "\n"
                    
                    if results:
                        page_confidence = sum([conf for (bbox, text, conf) in results]) / len(results)
                        total_confidence += page_confidence
                
                confidence = total_confidence / len(images) if len(images) > 0 else 0.0
                logger.info(f"EasyOCR: Processed {len(images)} pages, confidence: {confidence:.2f}")
                return extracted_text, confidence
            
            else:
                raise ValueError(f"Unsupported file type: {file_ext}")
                
        except Exception as e:
            logger.error(f"EasyOCR failed: {e}, falling back to Tesseract")
            # Fallback to Tesseract if EasyOCR fails
            return self._perform_tesseract_ocr(file_path, file_ext)
    
    def _parse_invoice_data(self, text: str) -> Dict[str, Any]:
        """
        Parse extracted text into structured invoice data
        
        Args:
            text: Extracted text from OCR
            
        Returns:
            Dictionary with parsed invoice fields
        """
        logger.info("Parsing invoice data from extracted text")
        
        data = {}
        
        # Extract vendor name - look for line after "Vendor:" or first substantial line after "INVOICE"
        vendor_match = re.search(r'Vendor[:\s]+([A-Za-z\s&\.,Ltd]+?)(?:\n|Invoice)', text, re.IGNORECASE | re.DOTALL)
        if vendor_match:
            data['vendor_name'] = vendor_match.group(1).strip()
        else:
            # Fallback: Try to get first line after INVOICE
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            for i, line in enumerate(lines):
                if 'INVOICE' in line.upper() and i + 1 < len(lines):
                    # Next non-empty line is likely vendor
                    next_line = lines[i + 1]
                    if not any(keyword in next_line.upper() for keyword in ['NUMBER', 'DATE', 'DESCRIPTION']):
                        data['vendor_name'] = next_line
                    break
        
        # Extract invoice number
        inv_num_match = re.search(r'Invoice\s+Number[:\s]+([A-Z0-9-]+)', text, re.IGNORECASE)
        if inv_num_match:
            data['invoice_number'] = inv_num_match.group(1).strip()
        
        # Extract invoice date
        date_match = re.search(r'Invoice\s+Date[:\s]+([0-9]{4}-[0-9]{2}-[0-9]{2})', text, re.IGNORECASE)
        if date_match:
            data['invoice_date'] = date_match.group(1).strip()
        
        # Extract due date
        due_match = re.search(r'Due\s+Date[:\s]+([0-9]{4}-[0-9]{2}-[0-9]{2})', text, re.IGNORECASE)
        if due_match:
            data['due_date'] = due_match.group(1).strip()
        
        # Extract line items - look for Description/Amount pattern
        line_items = []
        # Pattern: Description followed by amount on same or next line
        lines = text.split('\n')
        for i, line in enumerate(lines):
            # Skip header lines and summary lines
            if any(keyword in line.upper() for keyword in ['DESCRIPTION', 'INVOICE', 'VENDOR', 'DATE', 'SUBTOTAL', 'TOTAL', 'TAX']):
                continue
            
            # Look for lines with amounts ($X,XXX.XX format)
            amount_match = re.search(r'\$([0-9,]+\.?\d{0,2})', line)
            if amount_match:
                # Get description (everything before the amount)
                desc_part = line[:amount_match.start()].strip()
                
                # Skip if description contains summary keywords
                if any(keyword in desc_part.upper() for keyword in ['SUBTOTAL', 'TOTAL', 'TAX', 'BALANCE', 'DUE']):
                    continue
                
                if desc_part and len(desc_part) > 3:  # Meaningful description
                    amount = float(amount_match.group(1).replace(',', ''))
                    
                    # Try to find quantity in the line
                    # Look for standalone numbers (1, 2, 10, etc.)
                    qty_match = re.search(r'\b(\d+)\b', desc_part)
                    if qty_match:
                        quantity = int(qty_match.group(1))
                        # Remove quantity from description
                        desc_part = desc_part.replace(qty_match.group(0), '').strip()
                    else:
                        # Default to quantity 1 if not found
                        quantity = 1
                    
                    # Calculate unit price
                    unit_price = amount / quantity if quantity > 0 else amount
                    
                    line_items.append({
                        'description': desc_part,
                        'quantity': quantity,
                        'unit_price': unit_price,
                        'amount': amount
                    })
        
        data['line_items'] = line_items
        
        # Extract total amount - look for "Total" line
        total_match = re.search(r'Total[:\s]+\$([0-9,]+\.?\d{0,2})', text, re.IGNORECASE)
        if total_match:
            data['total_amount'] = float(total_match.group(1).replace(',', ''))
        
        # Extract subtotal
        subtotal_match = re.search(r'Subtotal[:\s]+\$([0-9,]+\.?\d{0,2})', text, re.IGNORECASE)
        if subtotal_match:
            data['subtotal'] = float(subtotal_match.group(1).replace(',', ''))
        
        # Extract tax amount
        tax_amt_match = re.search(r'Tax[:\s]+\$([0-9,]+\.?\d{0,2})', text, re.IGNORECASE)
        if tax_amt_match:
            data['tax_amount'] = float(tax_amt_match.group(1).replace(',', ''))
        
        logger.info(f"Parsed data: Vendor={data.get('vendor_name')}, Total=${data.get('total_amount')}, Items={len(line_items)}")
        
        return data


# Create node instance
extract_node = ExtractNode()

