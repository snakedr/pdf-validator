from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict
from uuid import UUID
from pydantic import BaseModel

from database import get_db
from models import Attachment as AttachmentModel, User as UserModel
from routers.auth import get_current_user, require_admin
from celery_client import celery_broker

router = APIRouter()

TASK_VALIDATE = "pdf_validator.validate_pdf_attachment"
TASK_SEND = "email_sender.send_pdf_attachment"

class TaskResponse(BaseModel):
    message: str
    task_id: str
    attachment_id: UUID

@router.post("/{attachment_id}/reprocess", response_model=TaskResponse)
async def reprocess_attachment(
    attachment_id: UUID,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin)
):
    """Запустить повторную обработку вложения (только админ)"""
    attachment = db.query(AttachmentModel).filter(AttachmentModel.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    if not attachment.file_path:
        raise HTTPException(status_code=400, detail="Attachment has no file_path")

    attachment.status = 'new'
    attachment.reject_reason = None
    attachment.validation_result = None
    attachment.gpt_response = None
    db.commit()

    task = celery_broker.send_task(TASK_VALIDATE, args=[str(attachment_id)])

    return TaskResponse(
        message="Reprocessing started",
        task_id=task.id,
        attachment_id=attachment_id
    )

@router.post("/{attachment_id}/resend", response_model=TaskResponse)
async def resend_attachment(
    attachment_id: UUID,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin)
):
    """Отправить вложение повторно (только админ)"""
    attachment = db.query(AttachmentModel).filter(AttachmentModel.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    if attachment.status not in ('validated', 'sent'):
        raise HTTPException(
            status_code=400,
            detail="Only validated or sent attachments can be resent"
        )

    attachment.sent_to_email = None
    attachment.sent_at = None
    db.commit()

    task = celery_broker.send_task(TASK_SEND, args=[str(attachment_id)])

    return TaskResponse(
        message="Resending started",
        task_id=task.id,
        attachment_id=attachment_id
    )

@router.post("/batch-reprocess", response_model=Dict[str, int])
async def batch_reprocess(
    attachment_ids: list[UUID],
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin)
):
    """Массовая переобработка вложений (только админ)"""
    processed = 0
    errors = 0
    to_send = []

    for attachment_id in attachment_ids:
        try:
            attachment = db.query(AttachmentModel).filter(AttachmentModel.id == attachment_id).first()
            if not attachment or not attachment.file_path:
                errors += 1
                continue

            attachment.status = 'new'
            attachment.reject_reason = None
            attachment.validation_result = None
            attachment.gpt_response = None

            to_send.append(str(attachment_id))
            processed += 1
        except Exception:
            errors += 1

    db.commit()

    for aid in to_send:
        celery_broker.send_task(TASK_VALIDATE, args=[aid])

    return {
        "processed": processed,
        "errors": errors,
        "total": len(attachment_ids)
    }

@router.post("/batch-resend", response_model=Dict[str, int])
async def batch_resend(
    attachment_ids: list[UUID],
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin)
):
    """Массовая повторная отправка вложений (только админ)"""
    processed = 0
    errors = 0
    to_send = []

    for attachment_id in attachment_ids:
        try:
            attachment = db.query(AttachmentModel).filter(AttachmentModel.id == attachment_id).first()
            if not attachment:
                errors += 1
                continue

            if attachment.status not in ('validated', 'sent'):
                errors += 1
                continue

            attachment.sent_to_email = None
            attachment.sent_at = None

            to_send.append(str(attachment_id))
            processed += 1
        except Exception:
            errors += 1

    db.commit()

    for aid in to_send:
        celery_broker.send_task(TASK_SEND, args=[aid])

    return {
        "processed": processed,
        "errors": errors,
        "total": len(attachment_ids)
    }

@router.get("/{attachment_id}/status")
async def get_attachment_status(
    attachment_id: UUID,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
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
