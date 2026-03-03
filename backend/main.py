from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
import os
from dotenv import load_dotenv

from database import get_db, create_tables
from models import Object, EmailSource, IncomingMessage, Attachment, Report
from logging_config import setup_logging

load_dotenv()

# Setup logging
logger = setup_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format_type=os.getenv("LOG_FORMAT", "json")
)

app = FastAPI(
    title="Email Processor API",
    description="API для обработки PDF-вложений из email",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В проде ограничить
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    logger.info("Starting Email Processor API")
    # Create tables if they don't exist
    create_tables()

@app.get("/")
async def root():
    return {"message": "Email Processor API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Pydantic models
from pydantic import BaseModel, EmailStr
from uuid import UUID
from datetime import datetime

class ObjectBase(BaseModel):
    name: str
    calculator_number: Optional[str] = None
    address: Optional[str] = None
    email: Optional[str] = None  # Can be comma-separated: "a@test.com, b@test.com"

class ObjectCreate(ObjectBase):
    pass

class ObjectUpdate(BaseModel):
    name: Optional[str] = None
    calculator_number: Optional[str] = None
    address: Optional[str] = None
    email: Optional[str] = None  # Can be comma-separated
    is_active: Optional[bool] = None

class Object(ObjectBase):
    id: UUID
    name_norm: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class EmailSourceBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None

class EmailSourceCreate(EmailSourceBase):
    pass

class EmailSourceUpdate(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    is_active: Optional[bool] = None

class EmailSource(EmailSourceBase):
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Include routers
from routers import objects, email_sources, messages, reports, actions

app.include_router(objects.router, prefix="/api/v1/objects", tags=["objects"])
app.include_router(email_sources.router, prefix="/api/v1/email-sources", tags=["email-sources"])
app.include_router(messages.router, prefix="/api/v1", tags=["messages"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])
app.include_router(actions.router, prefix="/api/v1/attachments", tags=["actions"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)