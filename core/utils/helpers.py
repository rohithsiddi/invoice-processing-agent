"""
Helper utilities for common operations
"""
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
import hashlib
import json


def generate_invoice_id(prefix: str = "INV") -> str:
    """
    Generate a unique invoice ID
    
    Args:
        prefix: Prefix for the ID
        
    Returns:
        Unique invoice ID
    """
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    unique_id = str(uuid.uuid4())[:8]
    return f"{prefix}-{timestamp}-{unique_id}"


def generate_checkpoint_id(invoice_id: str) -> str:
    """
    Generate a checkpoint ID for an invoice
    
    Args:
        invoice_id: Invoice identifier
        
    Returns:
        Checkpoint ID
    """
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    return f"CHKPT-{invoice_id}-{timestamp}"


def calculate_hash(data: Any) -> str:
    """
    Calculate SHA256 hash of data
    
    Args:
        data: Data to hash (will be JSON serialized)
        
    Returns:
        Hex digest of hash
    """
    json_str = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(json_str.encode()).hexdigest()


def calculate_tolerance(amount: float, tolerance_pct: float) -> tuple[float, float]:
    """
    Calculate tolerance range for an amount
    
    Args:
        amount: Base amount
        tolerance_pct: Tolerance percentage (e.g., 5.0 for 5%)
        
    Returns:
        Tuple of (min_amount, max_amount)
    """
    tolerance = amount * (tolerance_pct / 100.0)
    return (amount - tolerance, amount + tolerance)


def is_within_tolerance(
    value: float, 
    expected: float, 
    tolerance_pct: float
) -> bool:
    """
    Check if a value is within tolerance of expected value
    
    Args:
        value: Actual value
        expected: Expected value
        tolerance_pct: Tolerance percentage
        
    Returns:
        True if within tolerance
    """
    min_val, max_val = calculate_tolerance(expected, tolerance_pct)
    return min_val <= value <= max_val


def format_currency(amount: float, currency: str = "USD") -> str:
    """
    Format amount as currency
    
    Args:
        amount: Amount to format
        currency: Currency code
        
    Returns:
        Formatted currency string
    """
    if currency == "USD":
        return f"${amount:,.2f}"
    return f"{amount:,.2f} {currency}"


def parse_date(date_str: str) -> Optional[datetime]:
    """
    Parse date string in various formats
    
    Args:
        date_str: Date string
        
    Returns:
        Datetime object or None if parsing fails
    """
    formats = [
        '%Y-%m-%d',
        '%m/%d/%Y',
        '%d/%m/%Y',
        '%Y/%m/%d',
        '%d-%m-%Y',
        '%m-%d-%Y',
        '%B %d, %Y',
        '%d %B %Y'
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return None


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing invalid characters
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    import re
    # Remove invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip('. ')
    return sanitized


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to maximum length
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated
        
    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix



