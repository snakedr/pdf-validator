import imaplib
import os
from dotenv import load_dotenv

load_dotenv()

# Test IMAP connection
IMAP_SERVER = os.getenv("IMAP_SERVER")
IMAP_PORT = int(os.getenv("IMAP_PORT"))
IMAP_USER = os.getenv("IMAP_USER")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD")

print(f"Testing connection to: {IMAP_SERVER}:{IMAP_PORT}")
print(f"User: {IMAP_USER}")

try:
    client = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    result, data = client.login(IMAP_USER, IMAP_PASSWORD)
    print(f"✅ Login successful: {result}")
    
    # Check INBOX
    client.select('INBOX')
    result, data = client.search(None, 'ALL')
    print(f"📧 Total messages in INBOX: {len(data[0].split())}")
    
    # Check for recent messages
    result, data = client.search(None, 'FROM', 'noreply@eldis24.ru')
    print(f"📨 Messages from noreply@eldis24.ru: {len(data[0].split())}")
    
    client.logout()
    
except Exception as e:
    print(f"❌ Error: {e}")
