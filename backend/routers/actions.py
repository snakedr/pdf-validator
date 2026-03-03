from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Dict
from uuid import UUID
from pydantic import BaseModel

from database import get_db
from models import Attachment as AttachmentModel

router = APIRouter()

class TaskResponse(BaseModel):
    message: str
    task_id: str
    attachment_id: UUID

@router.post("/{attachment_id}/reprocess", response_model=TaskResponse)
async def reprocess_attachment(
    attachment_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Запустить повторную обработку вложения"""
    attachment = db.query(AttachmentModel).filter(AttachmentModel.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    # Reset status
    attachment.status = 'new'
    attachment.reject_reason = None
    attachment.validation_result = None
    attachment.gpt_response = None
    db.commit()
    
    # Add to processing queue
    task_id = f"reprocess_{attachment_id}_{attachment.created_at.timestamp()}"
    
    # Here you would normally queue the task with Celery
    # background_tasks.add_task(process_attachment_task, attachment_id)
    
    return TaskResponse(
        message="Reprocessing started",
        task_id=task_id,
        attachment_id=attachment_id
    )

@router.post("/{attachment_id}/resend", response_model=TaskResponse)
async def resend_attachment(
    attachment_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Отправить вложение повторно"""
    attachment = db.query(AttachmentModel).filter(AttachmentModel.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    if attachment.status != 'validated':
        raise HTTPException(
            status_code=400, 
            detail="Only validated attachments can be resent"
        )
    
    # Reset sent status
    attachment.sent_to_email = None
    attachment.sent_at = None
    db.commit()
    
    # Add to sending queue
    task_id = f"resend_{attachment_id}_{attachment.created_at.timestamp()}"
    
    # Here you would normally queue the task with Celery
    # background_tasks.add_task(send_attachment_task, attachment_id)
    
    return TaskResponse(
        message="Resending started",
        task_id=task_id,
        attachment_id=attachment_id
    )

@router.post("/batch-reprocess", response_model=Dict[str, int])
async def batch_reprocess(
    attachment_ids: list[UUID],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Массовая переобработка вложений"""
    processed = 0
    errors = 0
    
    for attachment_id in attachment_ids:
        try:
            attachment = db.query(AttachmentModel).filter(AttachmentModel.id == attachment_id).first()
            if not attachment:
                errors += 1
                continue
            
            # Reset status
            attachment.status = 'new'
            attachment.reject_reason = None
            attachment.validation_result = None
            attachment.gpt_response = None
            
            # Add to processing queue
            task_id = f"reprocess_{attachment_id}_{attachment.created_at.timestamp()}"
            # background_tasks.add_task(process_attachment_task, attachment_id)
            
            processed += 1
        except Exception:
            errors += 1
    
    db.commit()
    
    return {
        "processed": processed,
        "errors": errors,
        "total": len(attachment_ids)
    }

@router.post("/batch-resend", response_model=Dict[str, int])
async def batch_resend(
    attachment_ids: list[UUID],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Массовая повторная отправка вложений"""
    processed = 0
    errors = 0
    
    for attachment_id in attachment_ids:
        try:
            attachment = db.query(AttachmentModel).filter(AttachmentModel.id == attachment_id).first()
            if not attachment:
                errors += 1
                continue
                
            if attachment.status != 'validated':
                errors += 1
                continue
            
            # Reset sent status
            attachment.sent_to_email = None
            attachment.sent_at = None
            
            # Add to sending queue
            task_id = f"resend_{attachment_id}_{attachment.created_at.timestamp()}"
            # background_tasks.add_task(send_attachment_task, attachment_id)
            
            processed += 1
        except Exception:
            errors += 1
    
    db.commit()
    
    return {
        "processed": processed,
        "errors": errors,
        "total": len(attachment_ids)
    }

@router.get("/{attachment_id}/status")
async def get_attachment_status(attachment_id: UUID, db: Session = Depends(get_db)):
    """Получить статус обработки вложения"""
    attachment = db.query(AttachmentModel).filter(AttachmentModel.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    return {
        "id": attachment.id,
        "status": attachment.status,
        "reject_reason": attachment.reject_reason,
        "sent_to_email": attachment.sent_to_email,
        "sent_at": attachment.sent_at,
        "updated_at": attachment.updated_at
    }