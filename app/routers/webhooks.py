from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
import json

from app.core.db import get_db
from app.core.responses import BaseResponse
from app.core.security import verify_hmac_signature
from app.models.workflow import Workflow, WorkflowRun
from app.models.webhook import WebhookLog
from app.schemas.webhook import WebhookEventPayload
from app.services.workflow_executor import WorkflowExecutorService

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

@router.post("/{workflow_id}/trigger")
async def trigger_webhook(
    workflow_id: int, 
    request: Request,
    background_tasks: BackgroundTasks, 
    x_hub_signature_256: str = Header(None, alias="X-Hub-Signature-256"),
    db: AsyncSession = Depends(get_db)
):
    # 1. Read raw body and headers
    raw_payload = await request.body()
    headers = dict(request.headers)

    # 2. Extract JSON payload for logging
    try:
        json_payload = json.loads(raw_payload) if raw_payload else {}
    except json.JSONDecodeError:
        json_payload = {"raw": raw_payload.decode('utf-8', errors='ignore')}
        
    # 3. Create WebhookLog record immediately
    webhook_log = WebhookLog(
        workflow_id=workflow_id,
        headers=headers,
        payload=json_payload,
        status="accepted"
    )
    db.add(webhook_log)

    # 4. HMAC Verification
    if not verify_hmac_signature(raw_payload, x_hub_signature_256):
        webhook_log.status = "rejected"
        webhook_log.error_message = "Invalid or missing HMAC signature"
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 5. Fetch Workflow
    workflow = await db.get(Workflow, workflow_id)
    if not workflow or not workflow.is_active:
        webhook_log.status = "failed"
        webhook_log.error_message = "Workflow not found or inactive"
        await db.commit()
        raise HTTPException(status_code=404, detail="Workflow not available")

    # 6. Trigger workflow run
    run = WorkflowRun(workflow_id=workflow.id)
    db.add(run)
    await db.commit()
    await db.refresh(run)

    background_tasks.add_task(WorkflowExecutorService.execute_workflow, workflow.id, run.id, json_payload)

    # 7. Update WebhookLog
    webhook_log.status = "accepted"
    await db.commit()

    return BaseResponse(message="Webhook received and workflow triggered", data={"run_id": run.id})
