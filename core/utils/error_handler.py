"""
Error handling utilities with retry logic and failure management
"""
import time
import logging
from typing import Callable, Any, Optional, Dict, List
from functools import wraps
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RetryPolicy:
    """Retry policy configuration"""
    
    def __init__(
        self, 
        max_retries: int = 3, 
        backoff_seconds: float = 2.0,
        exponential: bool = True
    ):
        """
        Initialize retry policy
        
        Args:
            max_retries: Maximum number of retry attempts
            backoff_seconds: Base backoff time in seconds
            exponential: Use exponential backoff if True, constant if False
        """
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.exponential = exponential
    
    def get_backoff_time(self, attempt: int) -> float:
        """
        Calculate backoff time for a given attempt
        
        Args:
            attempt: Current attempt number (0-indexed)
            
        Returns:
            Backoff time in seconds
        """
        if self.exponential:
            return self.backoff_seconds * (2 ** attempt)
        return self.backoff_seconds


class InvoiceProcessingError(Exception):
    """Base exception for invoice processing errors"""
    
    def __init__(
        self, 
        message: str, 
        node: Optional[str] = None,
        recoverable: bool = True,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.node = node
        self.recoverable = recoverable
        self.details = details or {}
        self.timestamp = datetime.utcnow().isoformat()


class OCRError(InvoiceProcessingError):
    """OCR extraction failed"""
    pass


class ValidationError(InvoiceProcessingError):
    """Validation failed"""
    pass


class MatchingError(InvoiceProcessingError):
    """Matching failed"""
    pass


class ERPError(InvoiceProcessingError):
    """ERP integration error"""
    pass


class CheckpointError(InvoiceProcessingError):
    """Checkpoint persistence error"""
    pass


def with_retry(
    retry_policy: Optional[RetryPolicy] = None,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable] = None
):
    """
    Decorator to add retry logic to a function
    
    Args:
        retry_policy: RetryPolicy instance, defaults to 3 retries with 2s backoff
        exceptions: Tuple of exceptions to catch and retry
        on_retry: Optional callback function called on each retry
        
    Usage:
        @with_retry(retry_policy=RetryPolicy(max_retries=3))
        def my_function():
            # function code
            pass
    """
    if retry_policy is None:
        retry_policy = RetryPolicy()
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(retry_policy.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < retry_policy.max_retries:
                        backoff = retry_policy.get_backoff_time(attempt)
                        logger.warning(
                            f"Attempt {attempt + 1}/{retry_policy.max_retries + 1} failed for {func.__name__}: {e}. "
                            f"Retrying in {backoff}s..."
                        )
                        
                        if on_retry:
                            on_retry(attempt, e)
                        
                        time.sleep(backoff)
                    else:
                        logger.error(
                            f"All {retry_policy.max_retries + 1} attempts failed for {func.__name__}: {e}"
                        )
            
            # All retries exhausted
            raise last_exception
        
        return wrapper
    return decorator


class ErrorHandler:
    """
    Centralized error handler for the invoice processing workflow
    """
    
    def __init__(self, notify_ops_team: bool = True):
        """
        Initialize error handler
        
        Args:
            notify_ops_team: Whether to notify ops team on unrecoverable errors
        """
        self.notify_ops_team = notify_ops_team
        self.error_log: List[Dict[str, Any]] = []
    
    def handle_error(
        self, 
        error: Exception, 
        node: str,
        state: Optional[Dict[str, Any]] = None,
        persist_state: bool = True
    ) -> Dict[str, Any]:
        """
        Handle an error that occurred during workflow execution
        
        Args:
            error: The exception that occurred
            node: Name of the node where error occurred
            state: Current workflow state
            persist_state: Whether to persist state on unrecoverable error
            
        Returns:
            Error information dictionary
        """
        error_info = {
            'timestamp': datetime.utcnow().isoformat(),
            'node': node,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'recoverable': getattr(error, 'recoverable', True)
        }
        
        # Log the error
        self.error_log.append(error_info)
        logger.error(f"Error in {node}: {error}")
        
        # Handle based on recoverability
        if isinstance(error, InvoiceProcessingError) and not error.recoverable:
            return self._handle_unrecoverable_error(error, node, state, persist_state)
        
        return error_info
    
    def _handle_unrecoverable_error(
        self, 
        error: InvoiceProcessingError, 
        node: str,
        state: Optional[Dict[str, Any]] = None,
        persist_state: bool = True
    ) -> Dict[str, Any]:
        """
        Handle an unrecoverable error
        
        Args:
            error: The unrecoverable error
            node: Node where error occurred
            state: Current workflow state
            persist_state: Whether to persist state
            
        Returns:
            Error information with recovery actions
        """
        logger.critical(f"Unrecoverable error in {node}: {error}")
        
        error_info = {
            'timestamp': datetime.utcnow().isoformat(),
            'node': node,
            'error_type': type(error).__name__,
            'error_message': error.message,
            'recoverable': False,
            'action': 'persist_and_fail'
        }
        
        # Persist state if requested
        if persist_state and state:
            try:
                self._persist_failed_state(state, error_info)
                error_info['state_persisted'] = True
            except Exception as e:
                logger.error(f"Failed to persist state: {e}")
                error_info['state_persisted'] = False
        
        # Notify ops team
        if self.notify_ops_team:
            self._notify_ops_team(error_info, state)
        
        return error_info
    
    def _persist_failed_state(
        self, 
        state: Dict[str, Any], 
        error_info: Dict[str, Any]
    ):
        """
        Persist failed state to database
        
        Args:
            state: Workflow state to persist
            error_info: Error information
        """
        from core.models.database import get_session, AuditLog
        import uuid
        
        session = get_session()
        try:
            audit_entry = AuditLog(
                id=str(uuid.uuid4()),
                invoice_id=state.get('invoice_id', 'unknown'),
                node_name=error_info['node'],
                action='error_persist',
                result='failed',
                details={
                    'error': error_info,
                    'state': state
                }
            )
            session.add(audit_entry)
            session.commit()
            logger.info(f"Failed state persisted for invoice {state.get('invoice_id')}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to persist state to database: {e}")
            raise
        finally:
            session.close()
    
    def _notify_ops_team(
        self, 
        error_info: Dict[str, Any], 
        state: Optional[Dict[str, Any]] = None
    ):
        """
        Notify ops team about unrecoverable error
        
        Args:
            error_info: Error information
            state: Current workflow state
        """
        # In production, this would send email/Slack notification
        logger.critical(
            f"OPS TEAM NOTIFICATION: Unrecoverable error in {error_info['node']}\n"
            f"Error: {error_info['error_message']}\n"
            f"Invoice ID: {state.get('invoice_id') if state else 'unknown'}\n"
            f"Timestamp: {error_info['timestamp']}"
        )
        
        # TODO: Implement actual notification (email, Slack, PagerDuty, etc.)
    
    def get_error_summary(self) -> Dict[str, Any]:
        """
        Get summary of all errors
        
        Returns:
            Error summary statistics
        """
        total_errors = len(self.error_log)
        recoverable = sum(1 for e in self.error_log if e.get('recoverable', True))
        unrecoverable = total_errors - recoverable
        
        return {
            'total_errors': total_errors,
            'recoverable': recoverable,
            'unrecoverable': unrecoverable,
            'errors': self.error_log
        }


# Create singleton instance
error_handler = ErrorHandler()

