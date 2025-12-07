"""
State management utilities for workflow state operations
"""
from typing import Dict, Any, Optional
from datetime import datetime
import json
import copy

from core.models.state import InvoiceState


class StateManager:
    """
    Utility class for managing workflow state
    """
    
    @staticmethod
    def create_initial_state(invoice_id: str, file_path: str, file_type: str) -> InvoiceState:
        """
        Create initial workflow state
        
        Args:
            invoice_id: Unique invoice identifier
            file_path: Path to invoice file
            file_type: File type (pdf, png, jpg)
            
        Returns:
            Initial InvoiceState
        """
        return {
            'invoice_id': invoice_id,
            'file_path': file_path,
            'file_type': file_type,
            'status': 'PENDING',
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }
    
    @staticmethod
    def update_state(
        state: InvoiceState, 
        updates: Dict[str, Any],
        update_timestamp: bool = True
    ) -> InvoiceState:
        """
        Update state with new values
        
        Args:
            state: Current state
            updates: Dictionary of updates to apply
            update_timestamp: Whether to update the updated_at timestamp
            
        Returns:
            Updated state
        """
        updated_state = copy.deepcopy(state)
        updated_state.update(updates)
        
        if update_timestamp:
            updated_state['updated_at'] = datetime.utcnow().isoformat()
        
        return updated_state
    
    @staticmethod
    def serialize_state(state: InvoiceState) -> str:
        """
        Serialize state to JSON string
        
        Args:
            state: State to serialize
            
        Returns:
            JSON string
        """
        return json.dumps(state, indent=2, default=str)
    
    @staticmethod
    def deserialize_state(state_json: str) -> InvoiceState:
        """
        Deserialize state from JSON string
        
        Args:
            state_json: JSON string
            
        Returns:
            InvoiceState
        """
        return json.loads(state_json)
    
    @staticmethod
    def get_state_summary(state: InvoiceState) -> Dict[str, Any]:
        """
        Get a summary of the current state
        
        Args:
            state: Current state
            
        Returns:
            Summary dictionary
        """
        return {
            'invoice_id': state.get('invoice_id'),
            'status': state.get('status'),
            'invoice_type': state.get('invoice_type'),
            'vendor_name': state.get('extracted_data', {}).get('vendor_name'),
            'total_amount': state.get('extracted_data', {}).get('total_amount'),
            'match_result': state.get('match_result'),
            'approval_status': state.get('approval_status'),
            'posted': state.get('posted'),
            'created_at': state.get('created_at'),
            'updated_at': state.get('updated_at')
        }
    
    @staticmethod
    def validate_state(state: InvoiceState, required_fields: list) -> tuple[bool, list]:
        """
        Validate that state contains required fields
        
        Args:
            state: State to validate
            required_fields: List of required field names
            
        Returns:
            Tuple of (is_valid, missing_fields)
        """
        missing_fields = [
            field for field in required_fields
            if field not in state or state[field] is None
        ]
        
        return (len(missing_fields) == 0, missing_fields)
    
    @staticmethod
    def merge_states(base_state: InvoiceState, *updates: InvoiceState) -> InvoiceState:
        """
        Merge multiple state updates into base state
        
        Args:
            base_state: Base state
            *updates: Variable number of state updates
            
        Returns:
            Merged state
        """
        merged = copy.deepcopy(base_state)
        
        for update in updates:
            merged.update(update)
        
        merged['updated_at'] = datetime.utcnow().isoformat()
        
        return merged


class StateSnapshot:
    """
    Create and manage state snapshots for checkpointing
    """
    
    def __init__(self):
        self.snapshots: Dict[str, InvoiceState] = {}
    
    def save_snapshot(self, snapshot_id: str, state: InvoiceState):
        """
        Save a state snapshot
        
        Args:
            snapshot_id: Unique snapshot identifier
            state: State to snapshot
        """
        self.snapshots[snapshot_id] = copy.deepcopy(state)
    
    def load_snapshot(self, snapshot_id: str) -> Optional[InvoiceState]:
        """
        Load a state snapshot
        
        Args:
            snapshot_id: Snapshot identifier
            
        Returns:
            Snapshot state or None if not found
        """
        return copy.deepcopy(self.snapshots.get(snapshot_id))
    
    def delete_snapshot(self, snapshot_id: str):
        """
        Delete a snapshot
        
        Args:
            snapshot_id: Snapshot identifier
        """
        if snapshot_id in self.snapshots:
            del self.snapshots[snapshot_id]
    
    def list_snapshots(self) -> list:
        """
        List all snapshot IDs
        
        Returns:
            List of snapshot IDs
        """
        return list(self.snapshots.keys())


# Create singleton instances
state_manager = StateManager()
state_snapshot = StateSnapshot()

