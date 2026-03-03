import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os
from typing import Optional, Dict
import re
from datetime import datetime
import sys

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from celery_app import celery_app, SMTP_SERVER, SMTP_PORT, SMTP_USER, SMTP_PASSWORD
from utils import logger
from database import SessionLocal
from models import Attachment, Object

def transliterate(text: str) -> str:
    """Транслитерация русских букв в латиницу"""
    translit_dict = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '',
        'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo',
        'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
        'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
        'Ф': 'F', 'Х': 'H', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch', 'Ъ': '',
        'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
    }
    result = ''
    for char in text:
        result += translit_dict.get(char, char)
    return result

class EmailSender:
    def __init__(self):
        self.smtp_server = SMTP_SERVER or "localhost"
        self.smtp_port = SMTP_PORT or 587
        self.username = SMTP_USER or ""
        self.password = SMTP_PASSWORD or ""
    
    def create_safe_filename(self, object_name: str, address: str) -> str:
        """Создать безопасное имя файла из объекта и адреса"""
        # Remove special characters and normalize
        safe_object = re.sub(r'[^\w\s]', '', object_name).strip()
        safe_address = re.sub(r'[^\w\s.,-]', '', address).strip()
        
        # Combine and limit length
        filename = f"{safe_object} — {safe_address}.pdf"
        
        # Limit to reasonable length
        if len(filename) > 100:
            filename = filename[:97] + "..."
        
        return filename or "document.pdf"
    
    def send_email_with_pdf(
        self, 
        to_email: str, 
        subject: str, 
        body: str, 
        pdf_path: str, 
        pdf_filename: str
    ) -> Dict:
        """Отправить email с PDF вложением"""
        logger.info(f"[EMAIL] Starting send_email_with_pdf to {to_email}")
        try:
            logger.info("[EMAIL] Creating message...")
            # Create message
            message = MIMEMultipart()
            message["From"] = self.username
            message["To"] = to_email
            message["Subject"] = subject
            
            # Add body
            message.attach(MIMEText(body, "plain", "utf-8"))
            
            # Add PDF attachment
            if os.path.exists(pdf_path):
                with open(pdf_path, "rb") as attachment:
                    part = MIMEBase("application", "pdf")
                    part.set_payload(attachment.read())
                
                encoders.encode_base64(part)
                # Use RFC 5987 encoding for UTF-8 filename (without extra quotes)
                # Encode filename to UTF-8 bytes and then to percent-encoding
                filename_bytes = pdf_filename.encode('utf-8')
                encoded_filename = ''.join([f'%{b:02X}' for b in filename_bytes])
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename*=UTF-8''{encoded_filename}"
                )
                message.attach(part)
            else:
                raise Exception(f"PDF file not found: {pdf_path}")
            
            # Connect to SMTP server and send with timeout
            logger.info(f"[SMTP] Connecting to {self.smtp_server}:{self.smtp_port}")
            
            try:
                if self.smtp_port == 465:
                    # SSL connection for port 465
                    logger.info("[SMTP] Using SSL connection")
                    server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=10)
                else:
                    # STARTTLS for port 25/2525
                    logger.info("[SMTP] Using STARTTLS connection")
                    server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10)
                
                logger.info("[SMTP] Connection established")
                
                if self.smtp_port != 465:
                    logger.info("[SMTP] Starting TLS...")
                    server.starttls()
                    logger.info("[SMTP] TLS started")
                
                logger.info(f"[SMTP] Logging in as {self.username}")
                server.login(self.username, self.password)
                logger.info("[SMTP] Login successful")
                
                text = message.as_string()
                logger.info(f"[SMTP] Sending email to {to_email}...")
                
                server.sendmail(self.username, to_email, text)
                logger.info("[SMTP] Email sent successfully!")
                
                server.quit()
                logger.info("[SMTP] Connection closed")
                
            except Exception as e:
                logger.error(f"[SMTP] Error during send: {e}")
                raise
            
            logger.info(f"Email sent successfully to {to_email}")
            return {"status": "success", "to_email": to_email}
            
        except Exception as e:
            logger.error(f"Error sending email to {to_email}: {e}")
            return {"status": "error", "message": str(e)}
    
    def find_recipient_for_attachment(self, attachment: Attachment, db) -> Optional[str]:
        """Найти получателя для вложения по объекту"""
        try:
            # Try to match object by parsed object name from message
            if attachment.message and attachment.message.parsed_object:
                object_name = attachment.message.parsed_object
                normalized_name = re.sub(r'[^\w\s]', '', object_name.lower().strip())
                
                # Search for object in database
                obj = db.query(Object).filter(
                    Object.name_norm.contains(normalized_name),
                    Object.is_active == True
                ).first()
                
                if obj and obj.email:
                    return obj.email
            
            # If no match via parsed object, try direct object_id match
            if attachment.object_id:
                obj = db.query(Object).filter(
                    Object.id == attachment.object_id,
                    Object.is_active == True
                ).first()
                
                if obj and obj.email:
                    return obj.email
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding recipient for attachment {attachment.id}: {e}")
            return None

@celery_app.task(bind=True, max_retries=3)
def send_pdf_attachment(self, attachment_id: str):
    """Отправить PDF вложение найденному получателю"""
    logger.info(f"Starting to send attachment {attachment_id}")
    
    sender = EmailSender()
    db = SessionLocal()
    
    try:
        # Get attachment from DB
        attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
        if not attachment:
            logger.error(f"Attachment {attachment_id} not found")
            return {'status': 'error', 'message': 'Attachment not found'}
        
        if attachment.status not in ['approved', 'rejected']:
            logger.error(f"Attachment {attachment_id} cannot be sent (status: {attachment.status})")
            return {'status': 'error', 'message': f'Attachment status is {attachment.status}, cannot send'}
        
        # Determine recipients based on status
        recipients = []
        
        if attachment.status == 'approved':
            # Все поля заполнены - ищем объект по номеру вычислителя
            if attachment.calculator_number:
                # Ищем объект с таким номером вычислителя
                obj = db.query(Object).filter(
                    Object.calculator_number == attachment.calculator_number,
                    Object.is_active == True
                ).first()
                if obj and obj.email:
                    # Поддержка нескольких email через запятую
                    email_list = [e.strip() for e in obj.email.split(',') if e.strip()]
                    recipients.extend(email_list)
                    logger.info(f"Attachment {attachment_id} approved, found object {obj.name}, sending to {email_list}")
            
            # Если не нашли объект или у него нет email - отправляем на ddr@it37.ru (тестовый режим)
            if not recipients:
                recipients = ['ddr@it37.ru']
                logger.info(f"Attachment {attachment_id} approved, object not found or no email, sending to ddr@it37.ru")
        else:
            # rejected (есть пустые ячейки) - отправляем админам
            recipients = ['dv@it37.ru']
            logger.info(f"Attachment {attachment_id} rejected, sending to admin: dv@it37.ru")
        
        # Get object name and address from DB object or message
        object_name = None
        address = None
        
        # Try to get from object (if found by calculator number)
        if attachment.calculator_number:
            obj = db.query(Object).filter(
                Object.calculator_number == attachment.calculator_number,
                Object.is_active == True
            ).first()
            if obj:
                object_name = obj.name
                address = obj.address
        
        # Fallback to message parsing if object not found
        if not object_name:
            object_name = attachment.message.parsed_object or "Документ"
        if not address:
            address = attachment.message.parsed_address or "Без адреса"
        
        # Create filename: "Имя объекта - Адрес.pdf"
        safe_filename = f"{object_name} - {address}.pdf"
        
        # Clean filename from invalid characters
        safe_filename = re.sub(r'[<>"/\\|?*]', '', safe_filename)
        
        # Ensure .pdf extension
        if not safe_filename.lower().endswith('.pdf'):
            safe_filename += '.pdf'
        
        # Prepare email based on status
        if attachment.status == 'rejected':
            # Получаем информацию о пустых ячейках
            empty_cells_info = []
            if attachment.validation_result and 'tables' in attachment.validation_result:
                tables_result = attachment.validation_result['tables']
                empty_cells_info = tables_result.get('errors', [])
            
            subject = f"⚠️ ВНИМАНИЕ: Пропуски в данных - {object_name}"
            body = f"""
Здравствуйте!

Во вложении находится документ по объекту: {object_name}
Адрес: {address}

⚠️ ВНИМАНИЕ: В документе обнаружены пропуски в данных!

Проблемы ({len(empty_cells_info)}):
{chr(10).join(empty_cells_info[:10])}{'...' if len(empty_cells_info) > 10 else ''}

Дата получения: {attachment.created_at.strftime('%d.%m.%Y %H:%M')}

---
Это автоматическое сообщение, пожалуйста, не отвечайте на него.
            """
        else:
            subject = "Отчет о теплопотреблении"
            body = f"""
Здравствуйте!

Во вложении находится документ по объекту: {object_name}
Адрес: {address}

Дата получения: {attachment.created_at.strftime('%d.%m.%Y %H:%M')}

---
Это автоматическое сообщение, пожалуйста, не отвечайте на него.
            """
        
        # Send email to all recipients
        sent_to = []
        failed_to = []
        
        for recipient in recipients:
            try:
                result = sender.send_email_with_pdf(
                    to_email=recipient,
                    subject=subject,
                    body=body.strip(),
                    pdf_path=attachment.file_path,
                    pdf_filename=safe_filename
                )
                
                if result['status'] == 'success':
                    sent_to.append(recipient)
                    logger.info(f"Attachment {attachment_id} sent successfully to {recipient}")
                else:
                    failed_to.append(f"{recipient}: {result.get('message', 'unknown error')}")
                    logger.error(f"Failed to send attachment {attachment_id} to {recipient}: {result.get('message')}")
            except Exception as e:
                failed_to.append(f"{recipient}: {str(e)}")
                logger.error(f"Exception sending attachment {attachment_id} to {recipient}: {e}")
        
        # Если rejected - отправляем также np@it37.ru (в дополнение к основным)
        if attachment.status == 'rejected' and 'np@it37.ru' not in recipients:
            try:
                result = sender.send_email_with_pdf(
                    to_email='np@it37.ru',
                    subject=subject,
                    body=body.strip(),
                    pdf_path=attachment.file_path,
                    pdf_filename=safe_filename
                )
                if result['status'] == 'success':
                    sent_to.append('np@it37.ru')
                    logger.info(f"Attachment {attachment_id} also sent to np@it37.ru")
            except Exception as e:
                logger.error(f"Failed to send to np@it37.ru: {e}")
        
        # Update attachment status if at least one email was sent successfully
        if sent_to:
            attachment.status = 'sent'
            attachment.sent_to_email = ', '.join(sent_to)
            attachment.sent_at = datetime.utcnow()
            db.commit()
            
            return {
                'status': 'success',
                'recipient_email': ', '.join(sent_to),
                'filename': safe_filename,
                'failed': failed_to if failed_to else None
            }
        else:
            # All sends failed
            error_msg = '; '.join(failed_to) if failed_to else 'All sends failed'
            logger.error(f"Failed to send attachment {attachment_id} to all recipients: {error_msg}")
            
            # Mark as rejected after max retries
            if self.request.retries >= self.max_retries:
                attachment.status = 'rejected'
                attachment.reject_reason = 'send_error'
                db.commit()
            
            # Retry with exponential backoff
            if self.request.retries < self.max_retries:
                raise self.retry(countdown=60 * (2 ** self.request.retries))
            
            return {
                'status': 'error',
                'message': error_msg
            }
        
    except Exception as e:
        logger.error(f"Error sending attachment {attachment_id}: {e}")
        
        # Update attachment status
        attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
        if attachment:
            if self.request.retries >= self.max_retries:
                attachment.status = 'rejected'
                attachment.reject_reason = 'send_error'
                db.commit()
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60 * (2 ** self.request.retries))
        
        return {'status': 'error', 'message': str(e)}
    
    finally:
        db.close()