from typing import Any, Optional
from pydantic import BaseModel, EmailStr, Field

class LoginRequest(BaseModel):
    email: EmailStr

class ChatRequest(BaseModel):
    email: EmailStr
    message: str

class Action(BaseModel):
    intent: str = "UNKNOWN"
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    extra_data: Optional[str] = None
    updates: dict[str, Any] = Field(default_factory=dict)
    identifier: Optional[str] = None
