from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import shutil
import subprocess
import threading

from core.models.database import get_session, Checkpoint, Invoice, init_db
from core.utils.logging_config import get_logger

logger = get_logger(__name__)

# Initialize database on startup
try:
    init_db()
    logger.info("Database initialized successfully")
except Exception as e:
    logger.warning(f"Database initialization: {e}")

# Initialize templates
templates = Jinja2Templates(directory="app/api/templates")

app = FastAPI(
    title="Invoice Processing - Human Review API",
    description="API for human review of invoices that failed automatic matching",
    version="1.0.0"
)

# Track active workflows
active_workflows: Dict[str, Dict[str, Any]] = {}

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models
class PendingReviewItem(BaseModel):
    hitl_checkpoint_id: str
    invoice_id: str
    vendor_name: Optional[str] = None
    amount: Optional[float] = None
    created_at: str
    reason_for_hold: str
    review_url: str
    match_score: Optional[float] = None


class ReviewDecision(BaseModel):
    hitl_checkpoint_id: str
    decision: str  # ACCEPT or REJECT
    notes: str
    reviewer_id: str


class WorkflowStatus(BaseModel):
    workflow_id: str
    status: str
    current_stage: Optional[str] = None
    completed_stages: List[str] = []
    match_score: Optional[float] = None


class ReviewDecisionResponse(BaseModel):
    resume_token: str
    next_stage: str
    message: str


# API Endpoints


@app.get("/human-review/pending", response_model=List[PendingReviewItem])
async def list_pending_reviews():
    """
    List all pending review items
    
    Returns:
        List of pending invoices awaiting human review
    """
    session = get_session()
    try:
        # Query pending checkpoints
        checkpoints = session.query(Checkpoint).filter(
            Checkpoint.status == 'PENDING'
        ).order_by(Checkpoint.created_at.desc()).all()
        
        pending_items = []
        for checkpoint in checkpoints:
            # Parse state blob to get invoice details
            import json
            try:
                state = json.loads(checkpoint.state_blob)
                extracted_data = state.get('extracted_data', {})
                
                item = PendingReviewItem(
                    hitl_checkpoint_id=checkpoint.hitl_checkpoint_id,
                    invoice_id=checkpoint.invoice_id,
                    vendor_name=extracted_data.get('vendor_name'),
                    amount=extracted_data.get('total_amount'),
                    created_at=checkpoint.created_at.isoformat() if checkpoint.created_at else datetime.utcnow().isoformat(),
                    reason_for_hold=checkpoint.paused_reason or "Manual review required",
                    review_url=checkpoint.review_url or "",
                    match_score=state.get('match_score')
                )
                pending_items.append(item)
            except Exception as e:
                logger.error(f"Error parsing checkpoint {checkpoint.checkpoint_id}: {e}")
                continue
        
        logger.info(f"Retrieved {len(pending_items)} pending reviews")
        return pending_items
        
    except Exception as e:
        logger.error(f"Failed to retrieve pending reviews: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.get("/human-review/checkpoint/{hitl_checkpoint_id}")
async def get_checkpoint_details(hitl_checkpoint_id: str):
    """
    Get detailed information about a specific checkpoint
    
    Args:
        checkpoint_id: Checkpoint identifier
        
    Returns:
        Detailed checkpoint information including full state
    """
    session = get_session()
    try:
        checkpoint = session.query(Checkpoint).filter(
            Checkpoint.hitl_checkpoint_id == hitl_checkpoint_id
        ).first()
        
        if not checkpoint:
            raise HTTPException(status_code=404, detail="Checkpoint not found")
        
        # Parse state
        import json
        state = json.loads(checkpoint.state_blob)
        
        return {
            "hitl_checkpoint_id": checkpoint.hitl_checkpoint_id,
            "invoice_id": checkpoint.invoice_id,
            "status": checkpoint.status,
            "created_at": checkpoint.created_at.isoformat() if checkpoint.created_at else None,
            "paused_reason": checkpoint.paused_reason,
            "review_url": checkpoint.review_url,
            "state": state,
            "human_decision": checkpoint.human_decision,
            "reviewer_id": checkpoint.reviewer_id,
            "review_notes": checkpoint.review_notes,
            "reviewed_at": checkpoint.reviewed_at.isoformat() if checkpoint.reviewed_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get checkpoint details: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.post("/human-review/decision", response_model=ReviewDecisionResponse)
async def submit_review_decision(decision: ReviewDecision):
    """
    Submit human review decision for a checkpoint
    
    Args:
        decision: Review decision (ACCEPT or REJECT)
        
    Returns:
        Resume token and next stage information
    """
    session = get_session()
    try:
        # Validate decision
        if decision.decision not in ['ACCEPT', 'REJECT']:
            raise HTTPException(
                status_code=400,
                detail="Decision must be 'ACCEPT' or 'REJECT'"
            )
        
        # Find checkpoint
        checkpoint = session.query(Checkpoint).filter(
            Checkpoint.hitl_checkpoint_id == decision.hitl_checkpoint_id
        ).first()
        
        if not checkpoint:
            raise HTTPException(status_code=404, detail="Checkpoint not found")
        
        if checkpoint.status != 'PENDING':
            raise HTTPException(
                status_code=400,
                detail=f"Checkpoint already processed (status: {checkpoint.status})"
            )
        
        # Update checkpoint with decision
        checkpoint.human_decision = decision.decision
        checkpoint.reviewer_id = decision.reviewer_id
        checkpoint.review_notes = decision.notes
        checkpoint.status = 'REVIEWED'
        checkpoint.reviewed_at = datetime.now()
        
        session.commit()
        
        # Generate resume token
        resume_token = f"RESUME-{decision.hitl_checkpoint_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Determine next stage
        next_stage = 'RECONCILE' if decision.decision == 'ACCEPT' else 'COMPLETE'
        
        logger.info(
            f"Review decision submitted - Checkpoint: {decision.hitl_checkpoint_id}, "
            f"Decision: {decision.decision}, Reviewer: {decision.reviewer_id}"
        )
        
        # If accepted, resume workflow in background
        if decision.decision == 'ACCEPT':
            def resume_workflow():
                try:
                    import json
                    from app.workflow.invoice_workflow import get_compiled_workflow
                    
                    # Deserialize state
                    state = json.loads(checkpoint.state_blob)
                    
                    # Update state with human decision
                    state['human_decision'] = 'ACCEPT'
                    state['reviewer_id'] = decision.reviewer_id
                    state['status'] = 'APPROVED'
                    
                    # Get workflow
                    workflow = get_compiled_workflow()
                    config = {"configurable": {"thread_id": state['invoice_id']}}
                    
                    # Continue from RECONCILE
                    from app.nodes.reconcile_node import reconcile_node
                    from app.nodes.approve_node import approve_node
                    from app.nodes.post_node import post_node
                    from app.nodes.notify_node import notify_node
                    from app.nodes.complete_node import complete_node
                    
                    # Execute remaining nodes
                    state = reconcile_node(state)
                    state = approve_node(state)
                    state = post_node(state)
                    state = notify_node(state)
                    state = complete_node(state)
                    
                    logger.info(f"Workflow resumed and completed for {state['invoice_id']}")
                    
                except Exception as e:
                    logger.error(f"Failed to resume workflow: {e}", exc_info=True)
            
            # Start in background thread
            threading.Thread(target=resume_workflow, daemon=True).start()
        
        return ReviewDecisionResponse(
            resume_token=resume_token,
            next_stage=next_stage,
            message=f"Decision '{decision.decision}' recorded successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to submit review decision: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.get("/review", response_class=HTMLResponse)
async def serve_review_ui():
    """Serve the review HTML page"""
    html_path = Path(__file__).parent / "templates" / "review.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Review UI not found")
    return html_path.read_text()



@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


# ============================================================================
# Dashboard Endpoints
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    """Serve the main dashboard"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/erp-view", response_class=HTMLResponse)
async def serve_erp_view(request: Request):
    """Serve the ERP dashboard view"""
    return templates.TemplateResponse("erp_view.html", {"request": request})


@app.get("/api/erp-posted-invoices")
async def get_posted_invoices():
    """
    Get all posted invoices from the database
    
    Returns:
        List of posted invoices with ERP transaction details
    """
    session = get_session()
    try:
        # Query all invoices with status POSTED
        invoices = session.query(Invoice).filter(
            Invoice.status == 'POSTED'
        ).order_by(Invoice.created_at.desc()).all()
        
        result = []
        for inv in invoices:
            result.append({
                'invoice_id': inv.invoice_id,
                'invoice_number': inv.invoice_number,
                'vendor_name': inv.vendor_name,
                'total_amount': inv.total_amount,
                'invoice_date': inv.invoice_date,
                'erp_transaction_id': inv.erp_transaction_id,
                'approval_status': inv.approval_status,
                'status': inv.status,
                'created_at': inv.created_at.isoformat() if inv.created_at else None,
                'updated_at': inv.updated_at.isoformat() if inv.updated_at else None
            })
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to retrieve posted invoices: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.post("/api/process-invoice")
async def process_invoice(file: UploadFile = File(...)):
    """
    Upload and process an invoice
    
    Returns workflow_id for tracking
    """
    try:
        # Generate workflow ID
        workflow_id = f"WF-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        # Save uploaded file
        upload_dir = Path("data/uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = upload_dir / f"{workflow_id}_{file.filename}"
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        logger.info(f"File uploaded: {file_path}")
        
        # Initialize workflow status
        active_workflows[workflow_id] = {
            "status": "PROCESSING",
            "current_stage": "INGEST",
            "completed_stages": [],
            "file_path": str(file_path),
            "filename": file.filename,
            "match_score": None
        }
        
        # Start workflow in background
        def run_workflow():
            try:
                # Import workflow components
                from app.workflow.invoice_workflow import get_compiled_workflow
                from core.utils.state_manager import state_manager
                
                # Create initial state using state manager
                initial_state = state_manager.create_initial_state(
                    invoice_id=None,
                    file_path=str(file_path),
                    file_type=file_path.suffix.lstrip('.')
                )
                
                invoice_id = initial_state['invoice_id']
                thread_id = invoice_id
                
                # Get compiled workflow
                workflow = get_compiled_workflow()
                config = {"configurable": {"thread_id": thread_id}}
                
                # Track stages
                stages = ["INGEST", "EXTRACT", "CLASSIFY", "ENRICH", "VALIDATE", 
                         "RETRIEVE", "MATCH", "RECONCILE", "APPROVE", "POST", "NOTIFY", "COMPLETE"]
                
                stage_index = 0
                
                # Run workflow and track progress
                for output in workflow.stream(initial_state, config):
                    # Update progress
                    if stage_index < len(stages):
                        active_workflows[workflow_id]["current_stage"] = stages[stage_index]
                        active_workflows[workflow_id]["completed_stages"] = stages[:stage_index]
                        stage_index += 1
                    
                    # Check for match score in output
                    if isinstance(output, dict):
                        for node_output in output.values():
                            if isinstance(node_output, dict):
                                if 'match_score' in node_output:
                                    active_workflows[workflow_id]["match_score"] = node_output['match_score']
                
                # Mark as completed
                active_workflows[workflow_id]["status"] = "COMPLETED"
                active_workflows[workflow_id]["completed_stages"] = stages
                active_workflows[workflow_id]["current_stage"] = "COMPLETE"
                logger.info(f"Workflow {workflow_id} completed successfully")
                    
            except Exception as e:
                logger.error(f"Workflow error: {e}", exc_info=True)
                active_workflows[workflow_id]["status"] = "FAILED"
                active_workflows[workflow_id]["error"] = str(e)

        
        thread = threading.Thread(target=run_workflow, daemon=True)
        thread.start()
        
        return {"workflow_id": workflow_id, "status": "started"}
        
    except Exception as e:
        logger.error(f"Error processing invoice: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/workflow-status/{workflow_id}")
async def get_workflow_status(workflow_id: str):
    """Get current workflow status"""
    if workflow_id not in active_workflows:
        # Try to get from database
        session = get_session()
        try:
            invoice = session.query(Invoice).filter(
                Invoice.invoice_id.contains(workflow_id[-8:])
            ).first()
            
            if invoice:
                return {
                    "workflow_id": workflow_id,
                    "status": "COMPLETED",
                    "current_stage": "COMPLETE",
                    "completed_stages": ["INGEST", "EXTRACT", "CLASSIFY", "ENRICH", 
                                       "VALIDATE", "RETRIEVE", "MATCH", "RECONCILE",
                                       "APPROVE", "POST", "NOTIFY", "COMPLETE"],
                    "match_score": 1.0
                }
        finally:
            session.close()
        
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    return active_workflows[workflow_id]


@app.get("/api/recent-invoices")
async def get_recent_invoices():
    """Get list of recently processed invoices"""
    session = get_session()
    try:
        invoices = session.query(Invoice).order_by(
            Invoice.created_at.desc()
        ).limit(10).all()
        
        result = []
        for inv in invoices:
            try:
                created_at = inv.created_at.isoformat() if inv.created_at else datetime.now().isoformat()
            except:
                created_at = datetime.now().isoformat()
                
            result.append({
                "invoice_id": inv.invoice_number or inv.invoice_id,  # Show invoice number from document
                "vendor_name": inv.vendor_name or "Unknown",
                "amount": inv.total_amount or 0.0,
                "status": inv.status or "COMPLETED",
                "created_at": created_at
            })
        
        return result
    except Exception as e:
        logger.error(f"Error loading invoices: {e}")
        return []
    finally:
        session.close()


@app.get("/api/stats")
async def get_stats():
    """Get dashboard statistics"""
    session = get_session()
    try:
        total = session.query(Invoice).count()
        
        # Count by status
        pending = session.query(Checkpoint).filter(
            Checkpoint.human_decision == None
        ).count()
        
        approved = session.query(Invoice).filter(
            Invoice.status.in_(["APPROVED", "POSTED", "COMPLETED"])
        ).count()
        
        return {
            "total": total,
            "pending": pending,
            "approved": approved
        }
    except Exception as e:
        # Return zeros if tables don't exist yet
        logger.debug(f"Stats query failed (tables may not exist yet): {e}")
        return {
            "total": 0,
            "pending": 0,
            "approved": 0
        }
    finally:
        session.close()


if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Invoice Processing API on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info", access_log=False)
