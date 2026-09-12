from dataclasses import dataclass
from typing import Optional

@dataclass
class User:
    id: int
    name: str
    email: str
    phone: Optional[str] = None
    address: Optional[str] = None
    extra_data: Optional[str] = None
