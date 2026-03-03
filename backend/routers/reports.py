from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
import csv
import io

from database import get_db
from models import Attachment as AttachmentModel, Object as ObjectModel, IncomingMessage as MessageModel

router = APIRouter()

class RejectionReport(BaseModel):
    id: UUID
    filename: str
    reject_reason: str
    reject_details: Optional[dict]
    created_at: datetime
    object_name: Optional[str]
    message_subject: Optional[str]
    from_email: Optional[str]

class ReportSummary(BaseModel):
    total_attachments: int
    processed: int
    rejected: int
    sent: int
    rejected_by_reason: dict

@router.get("/rejections", response_model=List[RejectionReport])
async def get_rejection_report(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    reject_reason: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Получить отчет об отклоненных вложениях (JSON)"""
    query = db.query(AttachmentModel).outerjoin(ObjectModel).outerjoin(MessageModel).filter(
        AttachmentModel.status == 'rejected'
    )
    
    if date_from:
        query = query.filter(AttachmentModel.created_at >= date_from)
    if date_to:
        query = query.filter(AttachmentModel.created_at <= date_to)
    if reject_reason:
        query = query.filter(AttachmentModel.reject_reason == reject_reason)
    
    attachments = query.order_by(AttachmentModel.created_at.desc()).offset(skip).limit(limit).all()
    
    reports = []
    for attachment in attachments:
        reports.append(RejectionReport(
            id=attachment.id,
            filename=attachment.filename,
            reject_reason=attachment.reject_reason,
            reject_details=attachment.validation_result,
            created_at=attachment.created_at,
            object_name=attachment.object.name if attachment.object else None,
            message_subject=attachment.message.subject if attachment.message else None,
            from_email=attachment.message.from_email if attachment.message else None
        ))
    
    return reports

@router.get("/rejections.csv")
async def get_rejection_report_csv(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    reject_reason: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Экспорт отчета об отклоненных вложениях в CSV"""
    query = db.query(AttachmentModel).outerjoin(ObjectModel).outerjoin(MessageModel).filter(
        AttachmentModel.status == 'rejected'
    )
    
    if date_from:
        query = query.filter(AttachmentModel.created_at >= date_from)
    if date_to:
        query = query.filter(AttachmentModel.created_at <= date_to)
    if reject_reason:
        query = query.filter(AttachmentModel.reject_reason == reject_reason)
    
    attachments = query.order_by(AttachmentModel.created_at.desc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Headers
    writer.writerow([
        'ID', 'Filename', 'Reject Reason', 'Created At', 
        'Object Name', 'Message Subject', 'From Email', 'Validation Details'
    ])
    
    # Data
    for attachment in attachments:
        writer.writerow([
            str(attachment.id),
            attachment.filename,
            attachment.reject_reason,
            attachment.created_at.isoformat(),
            attachment.object.name if attachment.object else '',
            attachment.message.subject if attachment.message else '',
            attachment.message.from_email if attachment.message else '',
            str(attachment.validation_result) if attachment.validation_result else ''
        ])
    
    output.seek(0)
    
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),  # Add BOM for Excel
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=rejections_report.csv"}
    )

@router.get("/summary", response_model=ReportSummary)
async def get_report_summary(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: Session = Depends(get_db)
):
    """Получить сводный отчет"""
    query = db.query(AttachmentModel)
    
    if date_from:
        query = query.filter(AttachmentModel.created_at >= date_from)
    if date_to:
        query = query.filter(AttachmentModel.created_at <= date_to)
    
    # Get counts by status
    total_attachments = query.count()
    processed = query.filter(AttachmentModel.status.in_(['validated', 'sent', 'rejected'])).count()
    rejected = query.filter(AttachmentModel.status == 'rejected').count()
    sent = query.filter(AttachmentModel.status == 'sent').count()
    
    # Get rejection breakdown by reason
    rejected_by_reason = {}
    rejections = query.filter(AttachmentModel.status == 'rejected').all()
    for rejection in rejections:
        reason = rejection.reject_reason or 'unknown'
        rejected_by_reason[reason] = rejected_by_reason.get(reason, 0) + 1
    
    return ReportSummary(
        total_attachments=total_attachments,
        processed=processed,
        rejected=rejected,
        sent=sent,
        rejected_by_reason=rejected_by_reason
    )

@router.get("/processing-stats")
async def get_processing_stats(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: Session = Depends(get_db)
):
    """Получить статистику обработки по дням"""
    query = db.query(AttachmentModel)
    
    if date_from:
        query = query.filter(AttachmentModel.created_at >= date_from)
    if date_to:
        query = query.filter(AttachmentModel.created_at <= date_to)
    
    attachments = query.all()
    
    # Group by date
    daily_stats = {}
    for attachment in attachments:
        date_key = attachment.created_at.date().isoformat()
        if date_key not in daily_stats:
            daily_stats[date_key] = {
                'total': 0,
                'processed': 0,
                'rejected': 0,
                'sent': 0
            }
        
        daily_stats[date_key]['total'] += 1
        
        if attachment.status == 'rejected':
            daily_stats[date_key]['rejected'] += 1
        elif attachment.status == 'sent':
            daily_stats[date_key]['sent'] += 1
        
        if attachment.status in ['validated', 'sent', 'rejected']:
            daily_stats[date_key]['processed'] += 1
    
    return {
        'daily_stats': daily_stats,
        'total_days': len(daily_stats)
    }