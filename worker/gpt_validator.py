import json
from typing import Dict, Optional

from celery_app import celery_app, AI_API_KEY
from utils import logger
from database import get_db
from models import Attachment
from ai_client import ai_client

class GPTValidator:
    @staticmethod
    def prepare_gpt_prompt(validation_result: Dict, content_text: str, tables: list) -> str:
        """Подготовить промпт для GPT"""
        
        # Truncate text if too long
        max_text_length = 2000
        if len(content_text) > max_text_length:
            content_text = content_text[:max_text_length] + "..."
        
        # Prepare tables summary (limit to first few tables)
        tables_summary = []
        for i, table in enumerate(tables[:3]):  # Limit to first 3 tables
            rows = table.get('rows', [])
            if rows:
                tables_summary.append({
                    'table': i + 1,
                    'page': table.get('page'),
                    'sample_rows': rows[:5]  # First 5 rows
                })
        
        prompt = f"""
Ты - эксперт по анализу финансовых и технических документов. Проанализируй следующий PDF-документ и верни JSON-ответ с валидацией.

КОНТЕКСТ:
- Страниц в документе: {validation_result['extraction']['pages_count']}
- Найдено таблиц: {len(tables)}
- Детерминированная проверка дат: {"OK" if validation_result['deterministic_dates_ok'] else "FAILED"}
- Детерминированная проверка таблиц: {"OK" if validation_result['deterministic_tables_ok'] else "FAILED"}

ТЕКСТ ДОКУМЕНТА:
{content_text}

ТАБЛИЦЫ:
{json.dumps(tables_summary, ensure_ascii=False, indent=2)}

ДЕТЕРМИНИРОВАННАЯ ВАЛИДАЦИЯ:
{json.dumps(validation_result, ensure_ascii=False, indent=2)}

ЗАДАЧА:
Проанализируй документ и верни JSON с полями:
1. dates_match_current_month: true/false - соответствуют ли даты текущему месяцу
2. all_table_cells_are_numbers: true/false - содержат ли таблицы только числовые данные
3. document_is_valid: true/false - является ли документ валидным в целом
4. confidence_score: 0.0-1.0 - уверенность в валидации
5. notes: string - краткие замечания (максимум 200 символов)
6. detected_document_type: string - тип документа (счет, акт, отчет и т.д.)

ВАЖНО:
- Возвращай ТОЛЬКО JSON без дополнительного текста
- Будь строгим в валидации
- Учитывай контекст документа
"""

        return prompt
    
    @staticmethod
    def call_ai(document_text: str, tables: list) -> Optional[Dict]:
        """Вызвать универсальный AI API"""
        try:
            # Simple synchronous call for now
            import asyncio
            result = asyncio.run(ai_client.validate_document(document_text, tables))
            return result
        except Exception as e:
            logger.error(f"Error calling AI: {e}")
            return None

@celery_app.task(bind=True, max_retries=2)
def validate_with_gpt(self, attachment_id: str):
    """Валидация PDF с помощью GPT"""
    logger.info(f"Starting GPT validation for attachment {attachment_id}")
    
    with get_db() as db:
        try:
            # Get attachment from DB
            attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
            if not attachment:
                logger.error(f"Attachment {attachment_id} not found")
                return {'status': 'error', 'message': 'Attachment not found'}
            
            # Check if we have validation results
            if not attachment.validation_result:
                logger.error(f"No validation result for attachment {attachment_id}")
                return {'status': 'error', 'message': 'No validation result'}
            
            validation_result = attachment.validation_result
            
            # Skip GPT if OpenAI not configured
            if not OPENAI_API_KEY:
                logger.warning("OpenAI not configured, skipping GPT validation")
                # Assume deterministic validation is sufficient
                finalize_validation.delay(attachment_id)
                return {'status': 'skipped', 'reason': 'OpenAI not configured'}
            
            # Get PDF content for GPT
            from pdf_validator import PDFValidator
            content = PDFValidator.extract_text_and_tables(attachment.file_path)
            
            # Prepare prompt
            prompt = GPTValidator.prepare_gpt_prompt(
                validation_result, 
                content['text'], 
                content['tables']
            )
            
            # Call GPT
            gpt_result = GPTValidator.call_ai(
                content['text'], 
                content['tables']
            )
            
            if not gpt_result:
                logger.error(f"GPT validation failed for attachment {attachment_id}")
                # Fall back to deterministic validation only
                finalize_validation.delay(attachment_id)
                return {'status': 'error', 'message': 'GPT validation failed'}
            
            # Validate GPT response format
            required_fields = ['dates_match_current_month', 'all_table_cells_are_numbers', 
                             'document_is_valid', 'confidence_score', 'notes', 'detected_document_type']
            
            missing_fields = [field for field in required_fields if field not in gpt_result]
            if missing_fields:
                logger.error(f"GPT response missing fields: {missing_fields}")
                # Fall back to deterministic validation
                finalize_validation.delay(attachment_id)
                return {'status': 'error', 'message': 'Invalid GPT response format'}
            
            # Store GPT response
            attachment.gpt_response = gpt_result
            
            # Update validation result with GPT data
            validation_result['gpt'] = gpt_result
            validation_result['gpt_dates_ok'] = gpt_result.get('dates_match_current_month', False)
            validation_result['gpt_tables_ok'] = gpt_result.get('all_table_cells_are_numbers', False)
            validation_result['gpt_valid'] = gpt_result.get('document_is_valid', False)
            validation_result['gpt_confidence'] = gpt_result.get('confidence_score', 0.0)
            
            attachment.validation_result = validation_result
            
            db.commit()
            
            logger.info(f"GPT validation completed for attachment {attachment_id}")
            
            # Queue final validation decision
            finalize_validation.delay(attachment_id)
            
            return {
                'status': 'success',
                'gpt_result': gpt_result,
                'final_decision': 'queued'
            }
            
        except Exception as e:
            logger.error(f"Error in GPT validation for attachment {attachment_id}: {e}")
            
            # Retry with exponential backoff
            if self.request.retries < self.max_retries:
                raise self.retry(countdown=30 * (2 ** self.request.retries))
            
            # Fall back to deterministic validation
            finalize_validation.delay(attachment_id)
            return {'status': 'error', 'message': str(e)}

@celery_app.task
def finalize_validation(attachment_id: str):
    """Финализация валидации и принятие решения"""
    logger.info(f"Finalizing validation for attachment {attachment_id}")
    
    with get_db() as db:
        try:
            # Get attachment from DB
            attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
            if not attachment:
                logger.error(f"Attachment {attachment_id} not found")
                return {'status': 'error', 'message': 'Attachment not found'}
            
            validation_result = attachment.validation_result or {}
            
            # Get deterministic results
            deterministic_dates_ok = validation_result.get('deterministic_dates_ok', False)
            deterministic_tables_ok = validation_result.get('deterministic_tables_ok', False)
            
            # Get GPT results if available
            gpt_dates_ok = validation_result.get('gpt_dates_ok')
            gpt_tables_ok = validation_result.get('gpt_tables_ok')
            gpt_valid = validation_result.get('gpt_valid')
            gpt_confidence = validation_result.get('gpt_confidence', 0.0)
            
            # Make final decision
            if gpt_dates_ok is not None and gpt_tables_ok is not None:
                # Both deterministic and GPT validation available
                final_dates_ok = deterministic_dates_ok and gpt_dates_ok
                final_tables_ok = deterministic_tables_ok and gpt_tables_ok
                
                # Consider GPT confidence
                if gpt_confidence < 0.7:
                    final_valid = False
                else:
                    final_valid = final_dates_ok and final_tables_ok and gpt_valid
                
                reason = 'validated' if final_valid else 'gpt_validation'
                
            else:
                # Only deterministic validation available
                final_valid = deterministic_dates_ok and deterministic_tables_ok
                final_dates_ok = deterministic_dates_ok
                final_tables_ok = deterministic_tables_ok
                reason = 'validated' if final_valid else 'deterministic_validation'
            
            # Update validation result with final decision
            validation_result['final_dates_ok'] = final_dates_ok
            validation_result['final_tables_ok'] = final_tables_ok
            validation_result['final_valid'] = final_valid
            validation_result['final_reason'] = reason
            
            attachment.validation_result = validation_result
            
            if final_valid:
                attachment.status = 'validated'
                # Queue for sending
                from email_sender import send_pdf_attachment
                send_pdf_attachment.delay(attachment_id)
            else:
                attachment.status = 'rejected'
                # Determine reject reason
                if not final_dates_ok:
                    attachment.reject_reason = 'dates'
                elif not final_tables_ok:
                    attachment.reject_reason = 'tables'
                else:
                    attachment.reject_reason = 'validation'
            
            db.commit()
            
            logger.info(f"Validation finalized for attachment {attachment_id}: {attachment.status}")
            
            return {
                'status': 'success',
                'final_valid': final_valid,
                'attachment_status': attachment.status,
                'reason': reason
            }
            
        except Exception as e:
            logger.error(f"Error finalizing validation for attachment {attachment_id}: {e}")
            
            # Update attachment status to failed
            attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
            if attachment:
                attachment.status = 'rejected'
                attachment.reject_reason = 'validation_error'
                db.commit()
            
            return {'status': 'error', 'message': str(e)}