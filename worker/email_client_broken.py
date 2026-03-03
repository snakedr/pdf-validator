import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta
import os
from typing import List, Dict, Optional

from celery_app import celery_app, IMAP_SERVER, IMAP_PORT, IMAP_USER, IMAP_PASSWORD
from utils import logger
from database import SessionLocal
from models import IncomingMessage, EmailSource

class IMAPClient:
    def __init__(self):
        self.server = IMAP_SERVER
        self.port = IMAP_PORT
        self.username = IMAP_USER
        self.password = IMAP_PASSWORD
        self.connection = None
    
    def connect(self):
        """Подключиться к IMAP серверу"""
        try:
            self.connection = imaplib.IMAP4_SSL(self.server, self.port)
            self.connection.login(self.username, self.password)
            logger.info("Connected to IMAP server")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to IMAP: {e}")
            return False
    
    def disconnect(self):
        """Отключиться от IMAP сервера"""
        if self.connection:
            try:
                self.connection.logout()
                logger.info("Disconnected from IMAP server")
            except:
                pass
            self.connection = None
    
    def get_new_messages(self, days_back: int = 1) -> List[Dict]:
        """Получить новые письма за последние N дней"""
        if not self.connection:
            raise Exception("Not connected to IMAP server")
        
        try:
            # Select INBOX
            self.connection.select('INBOX')
            
            # Search for messages from last N days
            since_date = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")
            search_criteria = f'(SINCE {since_date})'
            
            status, messages = self.connection.search(None, search_criteria)
            if status != 'OK':
                return []
            
            message_ids = messages[0].split()
            logger.info(f"Found {len(message_ids)} messages")
            
            new_messages = []
            for msg_id in message_ids:
                try:
                    message_data = self._fetch_message(msg_id)
                    if message_data:
                        new_messages.append(message_data)
                except Exception as e:
                    logger.error(f"Error fetching message {msg_id}: {e}")
                    continue
            
            return new_messages
        
        except Exception as e:
            logger.error(f"Error getting messages: {e}")
            return []
    
    def _fetch_message(self, msg_id: bytes) -> Optional[Dict]:
        """Получить данные письма"""
        try:
            status, msg_data = self.connection.fetch(msg_id, '(RFC822)')
            if status != 'OK':
                return None
            
            raw_email = msg_data[0][1]
            email_message = email.message_from_bytes(raw_email)
            
            # Extract headers
            message_id = self._get_header(email_message, 'Message-ID')
            subject = self._decode_header(self._get_header(email_message, 'Subject'))
            from_email = self._get_header(email_message, 'From')
            date_str = self._get_header(email_message, 'Date')
            
            # Parse date
            received_at = None
            if date_str:
                try:
                    received_at = email.utils.parsedate_to_datetime(date_str)
                except:
                    received_at = datetime.utcnow()
            
            return {
                'provider_message_id': message_id,
                'from_email': from_email,
                'subject': subject,
                'received_at': received_at,
                'raw_content': raw_email
            }
            
        except Exception as e:
            logger.error(f"Error fetching message {msg_id}: {e}")
            return None
    
    def _get_header(self, email_message, header_name: str) -> str:
        """Получить заголовок письма"""
        if header_name in email_message:
            return email_message[header_name]
        return ""
    
    def _decode_header(self, header: str) -> str:
        """Декодировать заголовок"""
        if not header:
            return ""
        
        decoded_parts = decode_header(header)
        result = ""
        
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                if encoding:
                    result += part.decode(encoding, errors='ignore')
                else:
                    result += part.decode('utf-8', errors='ignore')
            else:
                result += part
        
        return result

def is_allowed_sender(from_email: str) -> bool:
    """Проверить, разрешен ли отправитель"""
    try:
        # Extract email from "Name <email@domain.com>" format
        if '<' in from_email and '>' in from_email:
            from_email = from_email.split('<')[1].split('>')[0]
        
        from_email = from_email.strip()
        
        # Hardcoded check for noreply@eldis24.ru
        return from_email == 'noreply@eldis24.ru'
    
    except Exception as e:
        logger.error(f"Error checking sender: {e}")
        return False

import traceback

@celery_app.task(bind=True)
def fetch_emails_task(self):
    """Основная задача получения и обработки писем"""
    logger.info("Starting email fetch task")
    
    client = IMAPClient()
    db = None
    
    try:
        if not client.connect():
            logger.error("Failed to connect to IMAP")
            return {'status': 'error', 'message': 'IMAP connection failed'}
        
        # Get messages from last 1 day (configurable)
        import sys
        print("DEBUG: About to get messages...", flush=True)
        sys.stdout.flush()
        messages = client.get_new_messages(days_back=1)
        print(f"DEBUG: Got {len(messages)} messages", flush=True)
        print(f"DEBUG: Got {len(messages)} messages")
        
        processed_count = 0
        error_count = 0
        
        # Create DB session
        print("DEBUG: About to create DB session...")
        db = SessionLocal()
        print("DEBUG: DB session created")
        
        for msg_data in messages:
            try:
                # Check if message already exists
                existing = db.query(IncomingMessage).filter(
                    IncomingMessage.provider_message_id == msg_data['provider_message_id']
                ).first()
                
                if existing:
                    logger.info(f"Message {msg_data['provider_message_id']} already exists")
                    continue
                
                # Check sender
                if not is_allowed_sender(msg_data['from_email']):
                    logger.info(f"Sender {msg_data['from_email']} not allowed")
                    continue
                
                # Create message record
                message = IncomingMessage(
                    provider_message_id=msg_data['provider_message_id'],
                    from_email=msg_data['from_email'],
                    subject=msg_data['subject'],
                    status='new',
                    received_at=msg_data['received_at']
                )
                
                db.add(message)
                db.commit()
                db.refresh(message)
                
                # Skip queue - just log
                logger.info(f"Would queue attachment processing for message {message.id}")
                
                processed_count += 1
                logger.info(f"Created message {message.id}")
                print(f"DEBUG: Created message {message.id}")
                
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing message: {e}")
                db.rollback()
                continue
        
        client.disconnect()
        
        logger.info(f"Processed {processed_count} messages, {error_count} errors")
        return {
            'status': 'success',
            'processed': processed_count,
            'errors': error_count
        }
        
    except Exception as e:
        logger.error(f"Email fetch task failed: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return {'status': 'error', 'message': str(e)}
    
    finally:
        client.disconnect()
        if db:
            db.close()