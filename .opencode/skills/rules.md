# Email Processor - Operating Rules

## Communication Rules

1. **Always ask before destructive operations** - Never delete, modify production data, or restart services without explicit user confirmation
2. **Explain what you're doing** - Briefly describe commands before running them
3. **Wait for confirmation** - Do not proceed with actions that require user approval

## Technical Rules

### Database Operations
- Always use parameterized queries
- Never delete production data without explicit confirmation
- Use SELECT queries to verify before UPDATE/DELETE

### Docker Operations
- Check logs before restarting: `docker compose logs service --tail=20`
- Verify changes were applied after rebuild

### Timezone Handling
- Celery Beat uses UTC by default
- Moscow time (MSK) = UTC + 3
- Example: MSK 9:00-23:00 = UTC 6:00-20:00

### PDF Validation
- Always verify object_name and address are extracted from PDF
- Check validation_result JSON for extraction results

## Response Style

- Be concise - 1-3 sentences maximum
- Answer directly without unnecessary preamble
- Use Russian language for user communication
- Use English for code comments and documentation
