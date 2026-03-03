import os
import pdfplumber
# import camelot  # отключен из-за OpenCV зависимостей
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json

from celery_app import celery_app
from utils import logger
from database import SessionLocal
from models import Attachment

class PDFValidator:
    @staticmethod
    def extract_text_and_tables(pdf_path: str) -> Dict:
        """Извлечь текст и таблицы из PDF"""
        try:
            result = {
                'text': '',
                'tables': [],
                'pages_count': 0,
                'extraction_errors': []
            }
            
            # Extract text with pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                result['pages_count'] = len(pdf.pages)
                
                for page_num, page in enumerate(pdf.pages):
                    try:
                        # Extract text
                        page_text = page.extract_text()
                        if page_text:
                            result['text'] += f"\n--- Page {page_num + 1} ---\n{page_text}"
                            
                            # Tables extraction disabled (camelot had OpenCV dependencies)
                            tables = []
                    except Exception as e:
                        result['extraction_errors'].append(f"Page {page_num + 1}: {str(e)}")
                        continue
        
        except Exception as e:
            logger.error(f"Error extracting PDF content: {e}")
            return {
                'text': '',
                'tables': [],
                'pages_count': 0,
                'extraction_errors': [str(e)]
            }
            
            # Extract text with pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                result['pages_count'] = len(pdf.pages)
                
                for page_num, page in enumerate(pdf.pages):
                    try:
                        # Extract text
                        page_text = page.extract_text()
                        if page_text:
                            result['text'] += f"\n--- Page {page_num + 1} ---\n{page_text}"
                            
                            # Tables extraction disabled (camelot had OpenCV dependencies)
                            tables = []
                    except Exception as e:
                        result['extraction_errors'].append(f"Page {page_num + 1}: {str(e)}")
                        continue
        
        return result
    
    @staticmethod
    def validate_dates(text: str) -> Dict:
        """Проверить даты в тексте"""
        try:
            # Ищем даты в формате ДД.ММ.ГГГГ
            date_pattern = r'\b\d{2}\.\d{2}\.\d{4}\b'
            dates = re.findall(date_pattern, text)
            
            # Проверяем валидность дат
            valid_dates = []
            for date_str in dates:
                try:
                    datetime.strptime(date_str, '%d.%m.%Y')
                    valid_dates.append(date_str)
                except ValueError:
                    continue
            
            # Даты OK если найдено хотя бы 3 валидные даты
            dates_ok = len(valid_dates) >= 3
            
            return {
                'dates_found': len(dates),
                'valid_dates': len(valid_dates),
                'dates': valid_dates,
                'dates_ok': dates_ok
            }
            
        except Exception as e:
            logger.error(f"Error validating dates: {e}")
            return {
                'dates_found': 0,
                'valid_dates': 0,
                'dates': [],
                'dates_ok': False,
                'error': str(e)
            }
    
    @staticmethod
    def validate_tables(tables: List[Dict]) -> Dict:
        """Проверить таблицы на числовые значения"""
        try:
            total_tables = len(tables)
            valid_tables = 0
            total_cells = 0
            numeric_cells = 0
            empty_cells = 0
            text_cells = 0
            table_details = []
            
            for i, table in enumerate(tables):
                rows = table.get('rows', [])
                table_valid = True
                table_numeric_cells = 0
                table_text_cells = 0
                table_empty_cells = 0
                
                for row_idx, row in enumerate(rows):
                    # Skip header row (usually first row)
                    if row_idx == 0:
                        continue
                    
                    for cell in row:
                        total_cells += 1
                        
                        if cell is None or str(cell).strip() == '':
                            empty_cells += 1
                            table_empty_cells += 1
                        else:
                            cell_str = str(cell).strip()
                            
                            # Check if numeric (allow decimals and basic formatting)
                            cell_str_clean = re.sub(r'[,\s]', '', cell_str)  # Remove commas and spaces
                            
                            if re.match(r'^-?\d+\.?\d*$', cell_str_clean):
                                numeric_cells += 1
                                table_numeric_cells += 1
                            else:
                                text_cells += 1
                                table_text_cells += 1
                                
                                # If non-numeric data found in data rows, table is invalid
                                table_valid = False
                
                if table_valid and len(rows) > 1:  # Must have header + data
                    valid_tables += 1
                
                table_details.append({
                    'table_index': i,
                    'page': table.get('page'),
                    'method': table.get('method'),
                    'rows_count': len(rows),
                    'is_valid': table_valid,
                    'numeric_cells': table_numeric_cells,
                    'text_cells': table_text_cells,
                    'empty_cells': table_empty_cells
                })
            
            # Determine overall validity
            tables_ok = total_tables > 0 and valid_tables > 0
            
            # Additional checks
            if total_tables > 0:
                numeric_ratio = numeric_cells / total_cells if total_cells > 0 else 0
                text_ratio = text_cells / total_cells if total_cells > 0 else 0
                
                # Tables are OK if most cells are numeric and we have valid tables
                tables_ok = tables_ok and numeric_ratio > 0.7 and text_ratio < 0.3
            
            return {
                'total_tables': total_tables,
                'valid_tables': valid_tables,
                'total_cells': total_cells,
                'numeric_cells': numeric_cells,
                'text_cells': text_cells,
                'empty_cells': empty_cells,
                'numeric_ratio': numeric_cells / total_cells if total_cells > 0 else 0,
                'text_ratio': text_cells / total_cells if total_cells > 0 else 0,
                'tables_ok': tables_ok,
                'table_details': table_details
            }
            
        except Exception as e:
            logger.error(f"Error validating tables: {e}")
            return {
                'total_tables': 0,
                'valid_tables': 0,
                'total_cells': 0,
                'numeric_cells': 0,
                'text_cells': 0,
                'empty_cells': 0,
                'tables_ok': False,
                'error': str(e)
            }

@celery_app.task(bind=True, max_retries=3)
def validate_pdf_attachment(self, attachment_id: str):
    """Основная задача валидации PDF"""
    logger.info(f"Starting PDF validation for attachment {attachment_id}")
    
    db = SessionLocal()
    try:
            # Get attachment from DB
            attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
            if not attachment:
                logger.error(f"Attachment {attachment_id} not found")
                return {'status': 'error', 'message': 'Attachment not found'}
            
            if not attachment.file_path or not os.path.exists(attachment.file_path):
                logger.error(f"File not found for attachment {attachment_id}")
                attachment.status = 'rejected'
                attachment.reject_reason = 'file_not_found'
                db.commit()
                return {'status': 'error', 'message': 'File not found'}
            
            # Update status to processing
            attachment.status = 'processing'
            db.commit()
            
            # Extract content
            content = PDFValidator.extract_text_and_tables(attachment.file_path)
            
            # Validate dates
            date_validation = PDFValidator.validate_dates(content['text'])
            
            # Validate tables
            table_validation = PDFValidator.validate_tables(content['tables'])
            
            # Compile validation result
            validation_result = {
                'extraction': {
                    'pages_count': content['pages_count'],
                    'text_length': len(content['text']),
                    'tables_found': len(content['tables']),
                    'extraction_errors': content['extraction_errors']
                },
                'dates': date_validation,
                'tables': table_validation,
                'deterministic_dates_ok': date_validation['dates_ok'],
                'deterministic_tables_ok': table_validation['tables_ok'],
                'overall_deterministic': date_validation['dates_ok'] and table_validation['tables_ok']
            }
            
            # Store validation result
            attachment.validation_result = validation_result
            
            # If deterministic validation passed, queue GPT validation
            if validation_result['overall_deterministic']:
                validate_with_gpt.delay(attachment_id)
            else:
                # Reject on deterministic validation failure
                if not date_validation['dates_ok']:
                    attachment.status = 'rejected'
                    attachment.reject_reason = 'dates'
                elif not table_validation['tables_ok']:
                    attachment.status = 'rejected'
                    attachment.reject_reason = 'tables'
                else:
                    attachment.status = 'rejected'
                    attachment.reject_reason = 'deterministic'
                
                db.commit()
            
            logger.info(f"Deterministic validation completed for attachment {attachment_id}")
            return {
                'status': 'success',
                'deterministic_result': validation_result['overall_deterministic'],
                'dates_ok': date_validation['dates_ok'],
                'tables_ok': table_validation['tables_ok']
            }
            
        except Exception as e:
            logger.error(f"Error validating PDF attachment {attachment_id}: {e}")
            
            # Update attachment status
            attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
            if attachment:
                attachment.status = 'rejected'
                attachment.reject_reason = 'validation_error'
                db.commit()
            
            # Retry with exponential backoff
            if self.request.retries < self.max_retries:
                raise self.retry(countdown=60 * (2 ** self.request.retries))
            
            return {'status': 'error', 'message': str(e)}
        finally:
            db.close()

@celery_app.task(bind=True, max_retries=3)
def validate_with_gpt(self, attachment_id: str):
    """GPT валидация PDF"""
    logger.info(f"Starting GPT validation for attachment {attachment_id}")
    
    db = SessionLocal()
    try:
            # Get attachment from DB
            attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
            if not attachment:
                logger.error(f"Attachment {attachment_id} not found")
                return {'status': 'error', 'message': 'Attachment not found'}
            
            # Здесь можно добавить логику GPT валидации
            # Пока просто одобряем
            attachment.status = 'approved'
            db.commit()
            
            logger.info(f"GPT validation completed for attachment {attachment_id}")
            return {'status': 'success', 'approved': True}
            
        except Exception as e:
            logger.error(f"Error in GPT validation for attachment {attachment_id}: {e}")
            
            # Update attachment status
            attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
            if attachment:
                attachment.status = 'rejected'
                attachment.reject_reason = 'gpt_validation_error'
                db.commit()
            
            # Retry with exponential backoff
            if self.request.retries < self.max_retries:
                raise self.retry(countdown=60 * (2 ** self.request.retries))
            
            return {'status': 'error', 'message': str(e)}
        finally:
            db.close()