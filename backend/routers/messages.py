from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel

from database import get_db
from models import IncomingMessage as MessageModel, Attachment as AttachmentModel, Object as ObjectModel

router = APIRouter()

# Pydantic models for messages and attachments
class MessageBase(BaseModel):
    pass

class Message(MessageBase):
    id: UUID
    provider_message_id: str
    source_id: UUID
    from_email: str
    subject: Optional[str]
    parsed_object: Optional[str]
    parsed_address: Optional[str]
    status: str
    error_message: Optional[str]
    received_at: datetime
    processed_at: Optional[datetime]

    class Config:
        from_attributes = True

class AttachmentBase(BaseModel):
    pass

class Attachment(AttachmentBase):
    id: UUID
    message_id: UUID
    object_id: Optional[UUID]
    filename: str
    file_path: Optional[str]
    file_sha256: str
    file_size: Optional[int]
    calculator_number: Optional[str]
    status: str
    reject_reason: Optional[str]
    validation_result: Optional[dict]
    gpt_response: Optional[dict]
    sent_to_email: Optional[str]
    sent_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True

class AttachmentWithObject(Attachment):
    object: Optional[dict] = None
    message: Optional[Message] = None

# Messages endpoints
@router.get("/messages", response_model=List[Message])
async def list_messages(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None),
    from_email: Optional[str] = Query(None),
    source_id: Optional[UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: Session = Depends(get_db)
):
    """Получить список входящих писем"""
    query = db.query(MessageModel)
    
    if status:
        query = query.filter(MessageModel.status == status)
    if from_email:
        query = query.filter(MessageModel.from_email.contains(from_email))
    if source_id:
        query = query.filter(MessageModel.source_id == source_id)
    if date_from:
        query = query.filter(MessageModel.received_at >= date_from)
    if date_to:
        query = query.filter(MessageModel.received_at <= date_to)
    
    return query.order_by(MessageModel.received_at.desc()).offset(skip).limit(limit).all()

@router.get("/messages/{message_id}", response_model=Message)
async def get_message(message_id: UUID, db: Session = Depends(get_db)):
    """Получить письмо по ID"""
    message = db.query(MessageModel).filter(MessageModel.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    return message

# Attachments endpoints
@router.get("/attachments", response_model=List[AttachmentWithObject])
async def list_attachments(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None),
    reject_reason: Optional[str] = Query(None),
    object_id: Optional[UUID] = Query(None),
    message_id: Optional[UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: Session = Depends(get_db)
):
    """Получить список вложений с фильтрами"""
    query = db.query(AttachmentModel).outerjoin(ObjectModel)
    
    if status:
        query = query.filter(AttachmentModel.status == status)
    if reject_reason:
        query = query.filter(AttachmentModel.reject_reason == reject_reason)
    if object_id:
        query = query.filter(AttachmentModel.object_id == object_id)
    if message_id:
        query = query.filter(AttachmentModel.message_id == message_id)
    if date_from:
        query = query.filter(AttachmentModel.created_at >= date_from)
    if date_to:
        query = query.filter(AttachmentModel.created_at <= date_to)
    
    attachments = query.order_by(AttachmentModel.created_at.desc()).offset(skip).limit(limit).all()
    
    # Add object info if available
    result = []
    for attachment in attachments:
        attachment_dict = attachment.__dict__.copy()
        if attachment.object:
            attachment_dict['object'] = {
                'id': attachment.object.id,
                'name': attachment.object.name,
                'email': attachment.object.email
            }
        result.append(AttachmentWithObject(**attachment_dict))
    
    return result

@router.get("/attachments/{attachment_id}", response_model=AttachmentWithObject)
async def get_attachment(attachment_id: UUID, db: Session = Depends(get_db)):
    """Получить детали вложения"""
    attachment = db.query(AttachmentModel).outerjoin(ObjectModel).filter(AttachmentModel.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    attachment_dict = attachment.__dict__.copy()
    if attachment.object:
        attachment_dict['object'] = {
            'id': attachment.object.id,
            'name': attachment.object.name,
            'email': attachment.object.email
        }
    
    return AttachmentWithObject(**attachment_dict)

@router.get("/attachments/{attachment_id}/details")
async def get_attachment_details(attachment_id: UUID, db: Session = Depends(get_db)):
    """Получить полную информацию о вложении включая результат проверок"""
    attachment = db.query(AttachmentModel).outerjoin(MessageModel).outerjoin(ObjectModel).filter(AttachmentModel.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    return {
        "id": attachment.id,
        "filename": attachment.filename,
        "file_path": attachment.file_path,
        "file_size": attachment.file_size,
        "status": attachment.status,
        "reject_reason": attachment.reject_reason,
        "validation_result": attachment.validation_result,
        "gpt_response": attachment.gpt_response,
        "sent_to_email": attachment.sent_to_email,
        "sent_at": attachment.sent_at,
        "created_at": attachment.created_at,
        "message": {
            "id": attachment.message.id,
            "subject": attachment.message.subject,
            "from_email": attachment.message.from_email,
            "received_at": attachment.message.received_at
        } if attachment.message else None,
        "object": {
            "id": attachment.object.id,
            "name": attachment.object.name,
            "address": attachment.object.address,
            "email": attachment.object.email
        } if attachment.object else None
    }