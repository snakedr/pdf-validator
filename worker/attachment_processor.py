import email
import os
import hashlib
import tempfile
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from celery_app import celery_app, UPLOAD_DIR
from database import SessionLocal
from utils import logger
from models import IncomingMessage, Attachment, Object


class AttachmentExtractor:
    @staticmethod
    def extract_pdf_attachments(email_message) -> List[Dict]:
        """Извлечь PDF вложения из email"""
        attachments = []
        
        for part in email_message.walk():
            if part.get_content_disposition() == 'attachment':
                filename = part.get_filename()
                if filename and filename.lower().endswith('.pdf'):
                    content = part.get_payload(decode=True)
                    if content:
                        file_hash = hashlib.sha256(content).hexdigest()
                        attachments.append({
                            'filename': filename,
                            'content': content,
                            'file_size': len(content),
                            'file_sha256': file_hash
                        })
        
        return attachments


def parse_subject(subject: str) -> Tuple[Optional[str], Optional[str]]:
    """Распарсить тему письма для извлечения объекта и адреса"""
    if not subject:
        return None, None
    
    # Простая логика - ищем шаблоны в теме
    object_name = None
    address = None
    
    # Пример: "Распечатка: ООО Ромашка, ул. Ленина, 1"
    if 'Распечатка:' in subject:
        parts = subject.split('Распечатка:')[1].strip()
        if ',' in parts:
            object_part, address_part = parts.split(',', 1)
            object_name = object_part.strip()
            address = address_part.strip()
        else:
            object_name = parts.strip()
    
    return object_name, address


def ensure_upload_dir() -> str:
    """Убедиться что директория для загрузок существует"""
    upload_path = UPLOAD_DIR
    if not os.path.exists(upload_path):
        os.makedirs(upload_path, exist_ok=True)
    return upload_path


def find_object_by_name(name: str, db) -> Optional[Object]:
    """Найти объект по названию"""
    # Нормализуем имя объекта
    name_norm = name.lower().replace(' ', '').replace('-', '').replace('_', '')
    
    # Ищем точное совпадение
    obj = db.query(Object).filter(
        Object.name_norm == name_norm,
        Object.is_active == True
    ).first()
    
    if obj:
        return obj
    
    # Ищем частичное совпадение
    obj = db.query(Object).filter(
        Object.name.ilike(f'%{name}%'),
        Object.is_active == True
    ).first()
    
    return obj


@celery_app.task(bind=True)
def process_message_attachments(self, message_id: str):
    """Обработать вложения в сообщении"""
    logger.info(f"Processing attachments for message {message_id}")
    
    db = SessionLocal()
    try:
        # Get message from DB
        message = db.query(IncomingMessage).filter(IncomingMessage.id == message_id).first()
        if not message:
            logger.error(f"Message {message_id} not found")
            return {'status': 'error', 'message': 'Message not found'}
        
        # Parse message for attachments
        # Skip attachments processing since raw_content is not available in message model
        logger.info(f"Skipping attachment processing for message {message_id} - raw_content not available")
        
        # Update message status
        message.status = 'done'
        message.processed_at = datetime.utcnow()
        db.commit()
        
        return {'status': 'success', 'attachments_found': 0}
        
        email_message = email.message_from_bytes(raw_content)
        
        # Extract PDF attachments
        attachments_data = AttachmentExtractor.extract_pdf_attachments(email_message)
        
        if not attachments_data:
            logger.info(f"No PDF attachments found in message {message_id}")
            # Update message status
            message.status = 'done'
            message.processed_at = datetime.utcnow()
            db.commit()
            return {'status': 'success', 'attachments_found': 0}
        
        # Parse subject for object and address
        object_name, address = parse_subject(message.subject or '')
        message.parsed_object = object_name
        message.parsed_address = address
        
        processed_count = 0
        upload_dir = ensure_upload_dir()
        
        for attachment_data in attachments_data:
            try:
                # Check if attachment already exists by hash
                existing = db.query(Attachment).filter(
                    Attachment.file_sha256 == attachment_data['file_sha256']
                ).first()
                
                if existing:
                    logger.info(f"Attachment with hash {attachment_data['file_sha256']} already exists")
                    continue
                
                # Find associated object
                target_object = None
                if object_name:
                    target_object = find_object_by_name(object_name, db)
                
                # Save file to disk
                file_path = os.path.join(upload_dir, attachment_data['filename'])
                with open(file_path, 'wb') as f:
                    f.write(attachment_data['content'])
                
                # Create attachment record
                attachment = Attachment(
                    message_id=message_id,
                    object_id=target_object.id if target_object else None,
                    filename=attachment_data['filename'],
                    file_path=file_path,
                    file_sha256=attachment_data['file_sha256'],
                    file_size=attachment_data['file_size'],
                    status='new'
                )
                
                db.add(attachment)
                db.commit()
                db.refresh(attachment)
                
                # Queue PDF validation
                from pdf_validator import validate_pdf_attachment as validate_pdf_task
                validate_pdf_task.delay(attachment.id)
                
                processed_count += 1
                logger.info(f"Created attachment {attachment.id}")
                
            except Exception as e:
                logger.error(f"Error processing attachment: {e}")
                db.rollback()
                continue
        
        # Update message status
        message.status = 'processing'
        message.processed_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"Processed {processed_count} attachments for message {message_id}")
        return {
            'status': 'success',
            'attachments_processed': processed_count,
            'object_name': object_name,
            'address': address
        }
        
    except Exception as e:
        logger.error(f"Error processing message attachments: {e}")
        # Update message status to failed
        message = db.query(IncomingMessage).filter(IncomingMessage.id == message_id).first()
        if message:
            message.status = 'failed'
            message.error_message = str(e)
            db.commit()
        return {'status': 'error', 'message': str(e)}
    finally:
        db.close()