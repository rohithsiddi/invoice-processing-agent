"""
LangGraph Workflow - Complete invoice processing workflow orchestrator
"""
from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from core.models.state import InvoiceState
from app.nodes.ingest_node import ingest_node
from app.nodes.extract_node import extract_node
from app.nodes.classify_node import classify_node
from app.nodes.enrich_node import enrich_node
from app.nodes.validate_node import validate_node
from app.nodes.retrieve_node import retrieve_node
from app.nodes.match_two_way_node import match_two_way_node
from app.nodes.checkpoint_hitl_node import checkpoint_hitl_node
from app.nodes.hitl_decision_node import hitl_decision_node
from app.nodes.reconcile_node import reconcile_node
from app.nodes.approve_node import approve_node
from app.nodes.post_node import post_node
from app.nodes.notify_node import notify_node
from app.nodes.complete_node import complete_node
from core.utils.logging_config import get_logger

logger = get_logger(__name__)


# Conditional edge functions
def should_checkpoint(state: InvoiceState) -> Literal["checkpoint", "reconcile"]:
    """
    Determine if workflow should pause for human review
    
    Args:
        state: Current workflow state
        
    Returns:
        "checkpoint" if match failed, "reconcile" if matched
    """
    match_result = state.get('match_result')
    
    if match_result == 'FAILED':
        logger.info("Match failed - routing to CHECKPOINT_HITL")
        return "checkpoint"
    else:
        logger.info("Match successful - routing to RECONCILE")
        return "reconcile"


def should_post(state: InvoiceState) -> Literal["post", "notify"]:
    """
    Determine if invoice should be posted to ERP
    
    Args:
        state: Current workflow state
        
    Returns:
        "post" if approved, "notify" if not approved
    """
    approval_status = state.get('approval_status')
    
    if approval_status in ['AUTO_APPROVED', 'HUMAN_APPROVED']:
        logger.info("Invoice approved - routing to POST")
        return "post"
    else:
        logger.info("Invoice not approved - routing to NOTIFY")
        return "notify"


def after_hitl_decision(state: InvoiceState) -> Literal["reconcile", "notify"]:
    """
    Determine next step after human decision
    
    Args:
        state: Current workflow state
        
    Returns:
        "reconcile" if accepted, "notify" if rejected
    """
    human_decision = state.get('human_decision')
    
    if human_decision == 'ACCEPT':
        logger.info("Human accepted - routing to RECONCILE")
        return "reconcile"
    else:
        logger.info("Human rejected - routing to NOTIFY")
        return "notify"


# Build the workflow graph
def create_workflow() -> StateGraph:
    """
    Create the complete invoice processing workflow
    
    Returns:
        Compiled StateGraph workflow
    """
    logger.info("Building invoice processing workflow")
    
    # Create graph
    workflow = StateGraph(InvoiceState)
    
    # Add all nodes
    workflow.add_node("ingest", ingest_node)
    workflow.add_node("extract", extract_node)
    workflow.add_node("classify", classify_node)
    workflow.add_node("enrich", enrich_node)
    workflow.add_node("validate", validate_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("match", match_two_way_node)
    workflow.add_node("checkpoint", checkpoint_hitl_node)
    workflow.add_node("hitl_decision", hitl_decision_node)
    workflow.add_node("reconcile", reconcile_node)
    workflow.add_node("approve", approve_node)
    workflow.add_node("post", post_node)
    workflow.add_node("notify", notify_node)
    workflow.add_node("complete", complete_node)
    
    # Define the workflow flow
    # Linear flow: INGEST → EXTRACT → CLASSIFY → ENRICH → VALIDATE
    workflow.set_entry_point("ingest")
    workflow.add_edge("ingest", "extract")
    workflow.add_edge("extract", "classify")
    workflow.add_edge("classify", "enrich")
    workflow.add_edge("enrich", "validate")
    
    # VALIDATE → RETRIEVE → MATCH
    workflow.add_edge("validate", "retrieve")
    workflow.add_edge("retrieve", "match")
    
    # Conditional: MATCH → CHECKPOINT (if failed) or RECONCILE (if matched)
    workflow.add_conditional_edges(
        "match",
        should_checkpoint,
        {
            "checkpoint": "checkpoint",
            "reconcile": "reconcile"
        }
    )
    
    # CHECKPOINT → HITL_DECISION (workflow pauses here in real implementation)
    workflow.add_edge("checkpoint", "hitl_decision")
    
    # Conditional: HITL_DECISION → RECONCILE (if accept) or NOTIFY (if reject)
    workflow.add_conditional_edges(
        "hitl_decision",
        after_hitl_decision,
        {
            "reconcile": "reconcile",
            "notify": "notify"
        }
    )
    
    # RECONCILE → APPROVE
    workflow.add_edge("reconcile", "approve")
    
    # Conditional: APPROVE → POST (if approved) or NOTIFY (if not)
    workflow.add_conditional_edges(
        "approve",
        should_post,
        {
            "post": "post",
            "notify": "notify"
        }
    )
    
    # POST → NOTIFY → COMPLETE → END
    workflow.add_edge("post", "notify")
    workflow.add_edge("notify", "complete")
    workflow.add_edge("complete", END)
    
    logger.info("Workflow graph built successfully")
    
    return workflow


# Compile workflow with checkpointer
def get_compiled_workflow():
    """
    Get compiled workflow with memory checkpointer and HITL interrupts
    
    Returns:
        Compiled workflow ready for execution
    """
    workflow = create_workflow()
    
    # Create memory checkpointer for state persistence
    # In production, use SqliteSaver or PostgresSaver
    checkpointer = MemorySaver()
    
    # Compile workflow with interrupt before HITL_DECISION
    # This pauses the workflow and waits for human review
    compiled_workflow = workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["hitl_decision"]  # Pause here for human review
    )
    
    logger.info("Workflow compiled with checkpointer and HITL interrupts")
    
    return compiled_workflow

