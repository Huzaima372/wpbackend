import os
from .database import is_allowed_email

def normalize_email(email: str) -> str:
    return email.strip().lower()

def authorize(email: str) -> bool:
    return is_allowed_email(normalize_email(email))

def llm_config() -> dict:
    enabled=os.getenv("LLM_ENABLED","false").lower()=="true"
    return {"enabled":enabled, "key_present":bool(os.getenv("OPENAI_API_KEY")),
            "model":os.getenv("OPENAI_MODEL","gpt-4o-mini"),
            "base_url":os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"}
