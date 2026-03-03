import email
from typing import List, Optional
import os
from datetime import datetime

from celery_app import celery_app, MAX_PDF_SIZE_MB
from utils import logger, get_file_sha256, sanitize_filename, ensure_upload_dir
from database import SessionLocal
from models import IncomingMessage, Attachment

class AttachmentExtractor:
    @staticmethod
    def extract_pdf_attachments(email_message) -> List[dict]:
        """Извлечь PDF вложения из письма"""
        attachments = []
        
        if email_message.is_multipart():
            for part in email_message.walk():
                # Skip multipart containers
                if part.get_content_maintype() == 'multipart':
                    continue
                
                # Check for PDF attachment
                content_disposition = part.get('Content-Disposition', '')
                content_type = part.get_content_type()
                
                if 'attachment' in content_disposition.lower() and content_type == 'application/pdf':
                    try:
                        attachment_data = AttachmentExtractor._process_attachment_part(part)
                        if attachment_data:
                            attachments.append(attachment_data)
                    except Exception as e:
                        logger.error(f"Error processing attachment: {e}")
                        continue
        
        return attachments
    
    @staticmethod
    def _process_attachment_part(part) -> Optional[dict]:
        """Обработать одну часть вложения"""
        try:
            filename = part.get_filename()
            if not filename:
                filename = 'unknown.pdf'
            
            # Get file content
            file_content = part.get_payload(decode=True)
            if not file_content:
                return None
            
            # Check file size
            max_size = MAX_PDF_SIZE_MB * 1024 * 1024
            if len(file_content) > max_size:
                logger.warning(f"Attachment {filename} too large: {len(file_content)} bytes")
                return None
            
            # Calculate hash
            file_sha256 = get_file_sha256(file_content)
            
            # Sanitize filename
            sanitized_filename = sanitize_filename(filename)
            
            return {
                'filename': sanitized_filename,
                'file_content': file_content,
                'file_sha256': file_sha256,
                'file_size': len(file_content)
            }
            
        except Exception as e:
            logger.error(f"Error processing attachment part: {e}")
            return None

def parse_subject(subject: str) -> tuple[Optional[str], Optional[str]]:
    """Распарсить тему письма на объект и адрес"""
    if not subject:
        return None, None
    
    import re
    
    # Pattern for "Object Name + Address"
    # Examples: "Объект 1 + ул. Ленина 123", "Здание А + г. Москва, ул. Тверская"
    patterns = [
        r'(.+?)\s*[+]\s*(.+)',  # "Object + Address"
        r'(.+?)\s*[-]\s*(.+)',  # "Object - Address" 
        r'(.+?)\s*[,]\s*(.+)',  # "Object, Address"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, subject, re.IGNORECASE)
        if match:
            object_name = match.group(1).strip()
            address = match.group(2).strip()
            
            # Basic validation
            if len(object_name) > 3 and len(address) > 3:
                return object_name, address
    
    # Try to extract address indicators if no clear separation
    address_keywords = ['ул.', 'улица', 'г.', 'город', 'д.', 'дом', 'кв.', 'квартира']
    for keyword in address_keywords:
        if keyword in subject.lower():
            # Try to split at the address keyword
            parts = subject.lower().split(keyword)
            if len(parts) >= 2:
                object_name = parts[0].strip()
                address = keyword + ' '.join(parts[1:]).strip()
                if len(object_name) > 3 and len(address) > 3:
                    return object_name.title(), address
    
    # If no clear pattern found, return None
    return None, None

def normalize_object_name(name: str) -> str:
    """Нормализовать имя объекта для поиска в БД"""
    if not name:
        return ''
    
    import re
    # Remove special characters and normalize
    normalized = re.sub(r'[^\w\s]', '', name.lower().strip())
    return normalized

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
            raw_content = message.raw_content if hasattr(message, 'raw_content') else None
            if not raw_content:
                logger.error(f"No raw content for message {message_id}")
                return {'status': 'error', 'message': 'No raw content'}
            
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
                    
                    # Save file to disk
                    file_path = os.path.join(upload_dir, attachment_data['file_sha256'] + '.pdf')
                    with open(file_path, 'wb') as f:
                        f.write(attachment_data['file_content'])
                    
                    # Create attachment record
                    attachment = Attachment(
                        message_id=message.id,
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