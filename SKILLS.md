# Email Processor System - Technical Skills

## Overview
Production-ready email processing system that automatically receives PDF reports from heat meters, validates them for data completeness, and routes them to appropriate recipients based on validation results.

## Architecture

### Components
- **Backend API**: FastAPI (port 8001)
- **Task Queue**: Celery + Redis
- **Scheduler**: Celery Beat with crontab
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Frontend**: Vanilla JS admin panel (port 4321)
- **File Storage**: Local filesystem (./uploads/)

### Docker Services
```
- postgres: PostgreSQL database
- redis: Message broker
- backend: FastAPI REST API
- worker: Celery task processor
- celery-beat: Scheduler daemon
- ui: Nginx static file server
```

## Processing Pipeline

### 1. Email Retrieval (IMAP)
**File**: `worker/email_client.py`
- Connects to: imap.timeweb.ru:993
- Mailbox: eldis@it37.ru
- Fetches emails from last 1 day
- Extracts Message-ID, From, Subject, Date
- Handles UTF-8 encoded subjects
- Extracts PDF attachments (application/pdf)
- Saves files with unique names: `{hash}_{original_name}.pdf`

### 2. Message Processing
**File**: `worker/attachment_processor.py`
- Parses email subject for object name and address
- Creates `incoming_messages` record
- Creates `attachments` record with status 'new'
- Calculates SHA256 hash for deduplication
- Queues for PDF validation

### 3. PDF Validation
**File**: `worker/pdf_validator.py`

#### Text Extraction
- Library: pdfplumber
- Extracts text from first 2 pages
- Extracts tables for validation

#### Calculator Number Extraction
Extracts device identifier from PDF content using patterns:
```
- Прибор: ТВ7 Заводской номер: {number}
- Теплосчетчик МКТС: №{number}
- ИД={number} (identifier)
- NT={number} (network number)
- №{number}
```

#### Object Info Extraction
```python
- Потребитель: {object_name}
- Адрес: {address} or Адрес объекта: {address}
```

#### Data Validation
- **Dates**: Checks all dates present (format: DD.MM.YYYY)
- **Tables**: Validates no "---" in data cells (rows starting with dates)
- **Empty Cells**: Counts cells with "---" value
- Status: 'approved' (no errors) or 'rejected' (has "---")

### 4. Email Sending
**File**: `worker/email_sender.py`

#### Approved Documents
1. Looks up object in database by calculator_number
2. If found with email(s): sends to all object's emails
3. Supports multiple recipients: `email1@domain.com, email2@domain.com`
4. If not found: sends to ddr@it37.ru (test mode)

#### Rejected Documents
- Sends to: dv@it37.ru and np@it37.ru
- Subject: "⚠️ ВНИМАНИЕ: Пропуски в данных - {object_name}"
- Includes error details in body

#### Multi-Address Support
- **Format**: Comma-separated email addresses
- **Example**: `director@company.ru, accountant@company.ru, manager@gmail.com`
- **Standard**: RFC 5322 compliant
- **Works with**: Gmail, Yandex, ProtonMail, Tuta, and any email provider

#### Email Format
- Subject: "Отчет о теплопотреблении"
- Filename format: "{object_name} - {address}.pdf"
- Encoding: UTF-8 with percent-encoding for attachment names
- Content-Type: application/pdf

## Database Schema

### Objects Table
```sql
- id (UUID, PK)
- name (String, required)
- name_norm (String, unique, normalized)
- calculator_number (String, unique, index)
- address (String, optional)
- email (String, for approved recipients)
- is_active (Boolean, default: true)
- created_at, updated_at (DateTime)
```

### Incoming Messages Table
```sql
- id (UUID, PK)
- provider_message_id (String, unique)
- source_id (UUID, FK to email_sources)
- from_email (String)
- subject (String)
- parsed_object (String, extracted from subject)
- parsed_address (String, extracted from subject)
- status (String: new, processing, done, failed)
- received_at (DateTime)
```

### Attachments Table
```sql
- id (UUID, PK)
- message_id (UUID, FK)
- object_id (UUID, FK to objects, nullable)
- filename (String, original filename)
- file_path (String, storage path)
- file_sha256 (String, unique, for deduplication)
- file_size (Integer)
- calculator_number (String, extracted from PDF)
- status (String: new, processing, validated, approved, rejected, sent)
- reject_reason (String: dates, tables, no_recipient, etc.)
- validation_result (JSONB, full validation data)
- sent_to_email (String)
- sent_at (DateTime)
- created_at, updated_at (DateTime)
```

## Schedule Configuration

### Celery Beat Schedule (celery_app.py)
```python
crontab(minute=0, hour=3)      # Daily cleanup at 03:00
crontab(minute=30, hour='3,9,15,21')  # Email check at 03:30, 09:30, 15:30, 21:30
```

### Timezone
- Europe/Moscow (UTC+3)

## API Endpoints

### Objects
- `GET /api/v1/objects/` - List all objects
- `POST /api/v1/objects/` - Create object
- `GET /api/v1/objects/{id}` - Get object details
- `PUT /api/v1/objects/{id}` - Update object
- `DELETE /api/v1/objects/{id}` - Delete object

### Email Sources
- `GET /api/v1/email-sources/` - List allowed senders
- `POST /api/v1/email-sources/` - Add sender
- `PUT /api/v1/email-sources/{id}` - Update sender

### Attachments/Documents
- `GET /api/v1/attachments/` - List all PDFs
- `GET /api/v1/attachments/?status={status}` - Filter by status
- `GET /api/v1/attachments/{id}` - Get details
- `POST /api/v1/attachments/{id}/reprocess` - Re-validate
- `POST /api/v1/attachments/{id}/resend` - Resend email

### Reports
- `GET /api/v1/reports/rejections?from=&to=` - JSON report
- `GET /api/v1/reports/rejections.csv?from=&to=` - CSV export

## Configuration Files

### Environment Variables (.env)
```bash
# Database
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/email_processor

# Redis
REDIS_URL=redis://redis:6379/0

# IMAP (Receiving)
IMAP_SERVER=imap.timeweb.ru
IMAP_PORT=993
IMAP_USER=eldis@it37.ru
IMAP_PASSWORD=IMAP_PASSWORD

# SMTP (Sending)
SMTP_SERVER=smtp.timeweb.ru
SMTP_PORT=587
SMTP_USER=noreply@eldis24.ru
SMTP_PASSWORD=SMTP_PASSWORD

# Storage
UPLOAD_DIR=./uploads
MAX_PDF_SIZE_MB=50

# AI (currently disabled)
AI_API_KEY=sk-...
AI_MODEL=gpt-4o-mini
```

## Validation Rules

### Approved (sent to object owner)
- No "---" in any table cell
- All dates present
- Calculator number extracted

### Rejected (sent to admins: dv@it37.ru + np@it37.ru)
- Contains "---" in data cells (missing values)
- Subject includes warning symbol ⚠️
- Body lists all problematic cells

## File Naming

### Original PDF (in uploads/)
Format: `{hash}_{original_filename}.pdf`
Example: `506247713506523e_Потребление ресурса (Объект).pdf`

### Sent PDF (email attachment)
Format: `{object_name} - {address}.pdf`
Example: `ТСЖ Наш дом - Иваново г, Сакко ул, д. 37А.pdf`

## Testing Workflow

1. Add object to database with:
   - name: "ТСЖ Наш дом"
   - calculator_number: "15017757"
   - email: "ddr@it37.ru" (or real recipient)
   - address: "Иваново г, Сакко ул, д. 37А"

2. Send test email with PDF to: eldis@it37.ru
   - Subject: "26-25 ТСЖ Наш дом г Иваново ул Сакко 37А (26.02.2026)"
   - PDF should contain: "Прибор: ТВ7 Заводской номер: 15017757"

3. Wait for scheduled check or run manually:
   ```python
   from email_client import fetch_emails_task
   fetch_emails_task.delay()
   ```

4. Check logs:
   ```bash
   docker compose logs worker --tail 50
   ```

5. Verify in UI: http://localhost:4321

## Common Commands

```bash
# View logs
docker compose logs worker --tail 100
docker compose logs celery-beat --tail 20

# Manual email check
docker compose exec worker python -c "from email_client import fetch_emails_task; fetch_emails_task.delay()"

# Database query
docker compose exec postgres psql -U postgres -d email_processor -c "SELECT * FROM attachments ORDER BY created_at DESC LIMIT 5;"

# Restart services
docker compose restart worker celery-beat

# Check schedule
docker compose logs celery-beat | grep "beat: Starting"

# Check systemd service status
sudo systemctl status docker-compose-project1

# View service logs
sudo journalctl -u docker-compose-project1 -f
```

## Autostart Configuration

### Systemd Service
System automatically starts on Debian boot via systemd service.

**Service file**: `/etc/systemd/system/docker-compose-project1.service`

```ini
[Unit]
Description=Email Processor Docker Compose
Requires=docker.service
After=docker.service network.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/root/project1
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

### Enable Autostart
```bash
# One-time setup
sudo systemctl enable docker
sudo systemctl enable docker-compose-project1
sudo systemctl start docker-compose-project1

# Verify
sudo systemctl is-enabled docker-compose-project1  # Should print: enabled
sudo systemctl is-active docker-compose-project1   # Should print: active
```

### Startup Order
1. Docker daemon starts
2. PostgreSQL container (waits for health check)
3. Redis container (waits for health check)
4. Backend, Worker, Celery Beat, UI containers start
5. Email processing resumes automatically

### Manual Control
```bash
# Stop all containers
sudo systemctl stop docker-compose-project1

# Start all containers
sudo systemctl start docker-compose-project1

# Restart
sudo systemctl restart docker-compose-project1
```

## Maintenance Tasks

### Daily (03:00)
- Cleans files older than 30 days
- Removes sent/rejected attachments from DB
- Deletes physical PDF files

### Health Check
- Database connectivity
- Recent message count
- Pending attachments count

## Known Issues & Limitations

1. **PDF Format Variations**: Different suppliers use different PDF formats. Extraction patterns may need updates for new formats.

2. **Encoding**: Some email clients may not display UTF-8 filenames correctly. System uses percent-encoding (RFC 5987) for compatibility.

3. **Test Mode**: If object not found in DB by calculator_number, sends to ddr@it37.ru instead of failing.

4. **GPT Validation**: Currently disabled in production. Only deterministic validation (regex + rules) is active.

5. **Single Mailbox**: System processes only one IMAP mailbox (eldis@it37.ru).

## Future Enhancements

1. Enable GPT validation for semantic checks
2. Add S3-compatible storage support
3. Implement webhook notifications
4. Add object auto-creation from parsed data
5. Multi-tenant support (multiple mailboxes)
6. PDF preview in UI
7. Bulk operations (bulk resend, bulk reprocess)

## Support Contacts

- System Admin: dv@it37.ru
- Notifications: np@it37.ru
- Test Recipient: ddr@it37.ru

---

**Version**: 1.1  
**Last Updated**: 2026-02-26  
**Status**: Production Ready

### Version History
- **v1.1**: Added multi-address email support, Docker autostart, systemd service
- **v1.0**: Initial production release with email processing, PDF validation, scheduling

## GitHub Security - Always Check
1. Пров

### Before Pushерить все файлы с реальными данными (*.json, *.md, *.yml)
2. Использовать `git grep` для поиска паролей и ключей:
   ```bash
   git grep -E "(password|passwd|pwd|secret|key|api|sk-)" --include="*.json" --include="*.md"
   ```
3. Проверить .gitignore - убедиться что secrets там есть
4. Никогда не пушить реальные пароли, API ключи, токены

### Files to Keep Private
- .env (реальные пароли и ключи)
- SKILLS.md (документация с примерами паролей)
- opencode.json (локальные настройки с API ключами)
- uploads/ (пользовательские данные)
