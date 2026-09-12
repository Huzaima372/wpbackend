from typing import Any
from .crud import create_user, delete_user_by_email, find_user_by_email, list_users, update_user_by_email
import re

EMAIL_RE=re.compile(r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\b")
PHONE_RE=re.compile(r"(?<!\w)\+?\d[\d\s().-]{5,}\d(?!\w)")
UPDATE_FIELDS={"name","phone","address","extra_data"}

def validate_email(v:Any)->str|None:
    return v.strip().lower() if isinstance(v,str) and EMAIL_RE.fullmatch(v.strip()) else None
def validate_name(v:Any)->str|None:
    return v.strip() if isinstance(v,str) and v.strip() else None
def validate_phone(v:Any)->str|None:
    if v is None or v=="": return None
    if not isinstance(v,str): return None
    n=re.sub(r"[\s().-]","",v.strip()); digits=re.sub(r"\D","",n)
    return v.strip() if 7<=len(digits)<=15 and n.lstrip("+").isdigit() else None

def create_user_tool(a:dict[str,Any])->dict[str,Any]:
    name=validate_name(a.get("name")); email=validate_email(a.get("email"))
    if not name: return {"message":"Name is required to add a user."}
    if not email: return {"message":"The email format is invalid."}
    if find_user_by_email(email): return {"message":f"Rejected: A user with email {email} already exists."}
    phone=validate_phone(a.get("phone"))
    if a.get("phone") and phone is None: return {"message":"The phone number is invalid."}
    address=a.get("address")
    if address is not None and (not isinstance(address,str) or not address.strip()): return {"message":"The address is invalid."}
    extra=a.get("extra_data")
    create_user(name,email,phone,address.strip() if isinstance(address,str) else None,extra.strip() if isinstance(extra,str) and extra.strip() else None)
    return {"message":f"User {email} was added successfully."}

def update_user_tool(a:dict[str,Any])->dict[str,Any]:
    email=validate_email(a.get("email") or a.get("identifier"))
    if not email: return {"message":"Please provide the user's email. Email is required for update."}
    if not find_user_by_email(email): return {"message":"No user exists with that email."}
    updates=a.get("updates") or {}
    if not updates and a.get("field") and a.get("value") is not None:
        field="address" if a["field"]=="city" else a["field"]
        if field=="email": return {"message":"Email cannot be changed through the normal update command."}
        updates={field:a["value"]}
    if not updates: return {"message":"Please specify the field and new value to update."}
    clean={}
    for field,value in updates.items():
        if field=="email": return {"message":"Email cannot be changed through the normal update command."}
        if field not in UPDATE_FIELDS: return {"message":f"The field '{field}' cannot be updated."}
        if field=="name":
            clean[field]=validate_name(value)
            if not clean[field]: return {"message":"The new name is invalid."}
        elif field=="phone":
            clean[field]=validate_phone(value)
            if value and not clean[field]: return {"message":"The phone number is invalid."}
        elif field=="address":
            if not isinstance(value,str) or not value.strip(): return {"message":"The new address is invalid."}
            clean[field]=value.strip()
        else:
            clean[field]=value.strip() if isinstance(value,str) else None
    update_user_by_email(email,clean)
    return {"message":f"User {email} was updated successfully."}

def delete_user_tool(a:dict[str,Any])->dict[str,Any]:
    email=validate_email(a.get("email") or a.get("identifier"))
    if not email: return {"message":"Please provide the user's email. Email is required for delete."}
    if not delete_user_by_email(email): return {"message":"No user exists with that email."}
    return {"message":f"User {email} was deleted."}

def list_users_tool(a:dict[str,Any]|None=None)->dict[str,Any]:
    users=list_users()
    return {"message":f"Found {len(users)} user(s)." if users else "There are no users in the system yet.","users":users}
