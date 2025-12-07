"""
Base node class for LangGraph workflow nodes
"""
from typing import Dict, Any, Optional, Callable
from abc import ABC, abstractmethod
from datetime import datetime
import logging
import uuid

from core.models.state import InvoiceState
from core.utils.error_handler import error_handler, with_retry, RetryPolicy

logger = logging.getLogger(__name__)


class BaseNode(ABC):
    """
    Abstract base class for all workflow nodes
    
    Each node should:
    1. Inherit from this class
    2. Implement the execute() method
    3. Update the state and return it
    """
    
    def __init__(
        self, 
        name: str,
        mode: str = "deterministic",
        retry_policy: Optional[RetryPolicy] = None
    ):
        """
        Initialize base node
        
        Args:
            name: Node name (e.g., "INGEST", "EXTRACT")
            mode: Node mode ("deterministic" or "non-deterministic")
            retry_policy: Optional retry policy for this node
        """
        self.name = name
        self.mode = mode
        self.retry_policy = retry_policy or RetryPolicy(max_retries=3, backoff_seconds=2.0)
    
    def __call__(self, state: InvoiceState) -> InvoiceState:
        """
        Make the node callable for LangGraph
        
        Args:
            state: Current workflow state
            
        Returns:
            Updated workflow state
        """
        return self.run(state)
    
    def run(self, state: InvoiceState) -> InvoiceState:
        """
        Run the node with error handling and audit logging
        
        Args:
            state: Current workflow state
            
        Returns:
            Updated workflow state
        """
        # Add visual separator for demo clarity
        logger.info(f"\n{'='*60}")
        logger.info(f"Starting node: {self.name}")
        logger.info(f"{'='*60}")
        start_time = datetime.utcnow()
        
        try:
            # Execute the node logic
            updated_state = self.execute(state)
            
            # Log successful execution
            self._log_audit(
                state=updated_state,
                action=f"{self.name}_execute",
                result="success",
                details={
                    'duration_ms': (datetime.utcnow() - start_time).total_seconds() * 1000
                }
            )
            
            logger.info(f"Completed node: {self.name}")
            logger.info(f"{'-'*60}\n")
            return updated_state
            
        except Exception as e:
            # Handle error
            error_info = error_handler.handle_error(
                error=e,
                node=self.name,
                state=state,
                persist_state=True
            )
            
            # Log failed execution
            self._log_audit(
                state=state,
                action=f"{self.name}_execute",
                result="failed",
                details={
                    'error': error_info,
                    'duration_ms': (datetime.utcnow() - start_time).total_seconds() * 1000
                }
            )
            
            logger.error(f"Failed node: {self.name} - {e}")
            
            # Re-raise if unrecoverable
            if not error_info.get('recoverable', True):
                raise
            
            # Return state with error information
            state['status'] = 'ERROR'
            state['error_info'] = error_info
            return state
    
    @abstractmethod
    def execute(self, state: InvoiceState) -> InvoiceState:
        """
        Execute the node logic (must be implemented by subclasses)
        
        Args:
            state: Current workflow state
            
        Returns:
            Updated workflow state
        """
        pass
    
    def _log_audit(
        self, 
        state: InvoiceState, 
        action: str, 
        result: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Log audit entry for this node's execution
        
        Args:
            state: Current workflow state
            action: Action performed
            result: Result of the action
            details: Additional details
        """
        from core.models.database import get_session, AuditLog
        
        session = get_session()
        try:
            audit_entry = AuditLog(
                id=str(uuid.uuid4()),
                invoice_id=state.get('invoice_id', 'unknown'),
                node_name=self.name,
                action=action,
                result=result,
                details=details or {}
            )
            session.add(audit_entry)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to log audit entry: {e}")
        finally:
            session.close()
    
    def validate_required_fields(
        self, 
        state: InvoiceState, 
        required_fields: list
    ):
        """
        Validate that required fields are present in state
        
        Args:
            state: Current workflow state
            required_fields: List of required field names
            
        Raises:
            ValueError: If required fields are missing
        """
        missing_fields = [
            field for field in required_fields 
            if field not in state or state[field] is None
        ]
        
        if missing_fields:
            raise ValueError(
                f"Missing required fields in {self.name}: {missing_fields}"
            )


class DeterministicNode(BaseNode):
    """
    Base class for deterministic nodes
    Deterministic nodes always produce the same output for the same input
    """
    
    def __init__(self, name: str, retry_policy: Optional[RetryPolicy] = None):
        super().__init__(name=name, mode="deterministic", retry_policy=retry_policy)


class NonDeterministicNode(BaseNode):
    """
    Base class for non-deterministic nodes
    Non-deterministic nodes may produce different outputs (e.g., LLM calls, human input)
    """
    
    def __init__(self, name: str, retry_policy: Optional[RetryPolicy] = None):
        super().__init__(name=name, mode="non-deterministic", retry_policy=retry_policy)


class ConditionalNode(BaseNode):
    """
    Base class for conditional nodes that route to different paths
    """
    
    def __init__(
        self, 
        name: str, 
        condition_func: Callable[[InvoiceState], str],
        retry_policy: Optional[RetryPolicy] = None
    ):
        """
        Initialize conditional node
        
        Args:
            name: Node name
            condition_func: Function that takes state and returns next node name
            retry_policy: Optional retry policy
        """
        super().__init__(name=name, mode="deterministic", retry_policy=retry_policy)
        self.condition_func = condition_func
    
    def execute(self, state: InvoiceState) -> InvoiceState:
        """
        Execute conditional logic
        
        Args:
            state: Current workflow state
            
        Returns:
            Updated state with next node information
        """
        next_node = self.condition_func(state)
        state['next_node'] = next_node
        return state

