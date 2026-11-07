from functools import lru_cache

from app.config import settings
from app.database.connection import SessionLocal
from app.email.sender import get_mail_gateway
from app.processor import EmailProcessor


@lru_cache
def get_processor() -> EmailProcessor:
    return EmailProcessor(SessionLocal, get_mail_gateway(), settings)
