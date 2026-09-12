import json
import os
import re
import logging
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))
logger = logging.getLogger(__name__)
_last_llm_error: str | None = None

from .crud import (
    create_user,
    delete_user_by_email,
    find_user_by_email,
    list_users,
    update_user_by_email,
)

EMAIL_RE = re.compile(r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\b")
PHONE_RE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{5,}\d(?!\w)")
VALID_INTENTS = {"CREATE_USER", "UPDATE_USER", "DELETE_USER", "LIST_USERS", "UNKNOWN"}
UPDATE_FIELDS = {"name", "phone", "address", "extra_data"}

SYSTEM_PROMPT = """
You are a command router for an admin user-management application.
Return JSON only. Never execute tools, SQL, or database operations.

Intents:
CREATE_USER, UPDATE_USER, DELETE_USER, LIST_USERS, UNKNOWN

Schema:
{
  "intent": "...",
  "name": null,
  "email": null,
  "phone": null,
  "address": null,
  "extra_data": null,
  "updates": {},
  "identifier": null
}

Rules:
- CREATE_USER requires name and email; phone/address/extra_data are optional.
- UPDATE_USER MUST use email as the identifier. updates may contain only name, phone,
  address, extra_data. Never use update to change email.
- DELETE_USER MUST use email as identifier.
- LIST_USERS has no fields.
- Do not invent missing values.
- Do not produce SQL.
"""


def empty_action(intent: str = "UNKNOWN") -> dict[str, Any]:
    return {
        "intent": intent, "name": None, "email": None, "phone": None,
        "address": None, "extra_data": None, "updates": {}, "identifier": None,
    }


def _clean_phone(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    return value if PHONE_RE.fullmatch(value) else None


def _extract_labeled_value(text: str, labels: list[str]) -> str | None:
    pattern = r"(?:%s)\s*(?:is|=|:)?\s*([^,]+)" % "|".join(map(re.escape, labels))
    match = re.search(pattern, text, re.I)
    return match.group(1).strip() if match else None


def local_parse(text: str) -> dict[str, Any]:
    """Safe fallback router. Routing is explicit; CRUD never happens here."""
    t = text.strip()
    low = t.lower()
    emails = EMAIL_RE.findall(t)

    # LIST has highest priority when it is clearly a listing request.
    if re.search(r"\b(show|list|display)\b.*\b(all\s+)?users?\b", low) or low in {
        "users", "all users", "list", "show users"
    }:
        return empty_action("LIST_USERS")

    # UPDATE is deliberately checked BEFORE CREATE so 'update ...' can never become add.
    if re.search(r"\b(update|change|modify|edit|set)\b", low):
        email = emails[0] if emails else None
        field = None
        for candidate in ("phone", "address", "city", "name", "email"):
            if re.search(rf"\b{candidate}\b", low):
                field = candidate
                break

        if not email:
            return {**empty_action("UPDATE_USER"), "identifier": None, "field": field}

        # Accept "city" as a natural-language alias but store it as address.
        field = "address" if field == "city" else field
        if field == "email":
            return {**empty_action("UPDATE_USER"), "identifier": email, "email": email,
                    "field": "email"}

        value = None
        if field:
            patterns = [
                rf"\b{re.escape(field)}\b\s+(?:to|as)\s+(.+)$",
                rf"\b{re.escape(field)}\b\s*[:=]\s*(.+)$",
            ]
            for pattern in patterns:
                match = re.search(pattern, t, re.I)
                if match:
                    value = match.group(1).strip().strip("\"'")
                    break
            # If the command used "city", search that original token.
            if value is None and field == "address":
                match = re.search(r"\bcity\b\s+(?:to|as)\s+(.+)$", t, re.I)
                if match:
                    value = match.group(1).strip().strip("\"'")
        result = {**empty_action("UPDATE_USER"), "identifier": email, "email": email,
                  "field": field, "value": value}
        if field and value is not None:
            result["updates"] = {field: value}
        return result

    # DELETE only accepts email. Never fall back to name/phone.
    if re.search(r"\b(delete|remove|erase)\b", low):
        email = emails[0] if emails else None
        return {**empty_action("DELETE_USER"), "identifier": email, "email": email}

    # CREATE comes after UPDATE/DELETE to protect routing.
    if re.search(r"\b(add|create|register)\b", low):
        email = emails[0] if emails else None
        result = empty_action("CREATE_USER")
        result["email"] = email

        # Name is extracted only from explicit natural-language patterns.
        name_match = re.search(
            r"\b(?:add|create|register)\s+(?:a\s+)?(?:new\s+)?(?:user\s+)?"
            r"([A-Za-z][A-Za-z .'-]*?)(?=\s+(?:with|and|email)\b|,|$)",
            t, re.I,
        )
        if name_match:
            candidate = name_match.group(1).strip()
            if candidate.lower() not in {"with", "email", "user", "new"}:
                result["name"] = candidate

        # Prefer an explicitly supplied phone value, including values that are
        # obviously invalid; validation must reject those rather than silently
        # dropping the field.
        phone_match = re.search(
            r"\bphone(?:\s+number)?\b\s*(?:is|=|:|to)?\s*(.+?)(?=\s*(?:,|;|$|\band\s+(?:address|city|email|department|company|role|title)\b))", t, re.I
        )
        if phone_match:
            result["phone"] = phone_match.group(1).strip()
        else:
            phone_match = PHONE_RE.search(t)
            if phone_match:
                result["phone"] = phone_match.group(0).strip()

        address = _extract_labeled_value(t, ["address", "city"])
        if address:
            result["address"] = address

        # Capture explicit department/company/etc. without throwing it away.
        extras = []
        for label, value in re.findall(
            r"\b(department|company|role|title|country|organization)\s*(?:is|=|:)?\s*([^,]+)",
            t, re.I
        ):
            extras.append(f"{label}: {value.strip()}")
        if extras:
            result["extra_data"] = ", ".join(extras)
        return result

    return empty_action()


def _sanitize_llm_action(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    intent = str(raw.get("intent", "UNKNOWN")).upper().strip()
    if intent not in VALID_INTENTS:
        return None

    result = empty_action(intent)
    for key in ("name", "email", "address", "extra_data", "identifier"):
        value = raw.get(key)
        if isinstance(value, str):
            result[key] = value.strip()

    # LLMs sometimes emit phone numbers as JSON numbers (for example 923321234567)
    # even though the application schema expects text. Normalize them here instead
    # of rejecting an otherwise valid phone number.
    raw_phone = raw.get("phone")
    if isinstance(raw_phone, (str, int, float)) and not isinstance(raw_phone, bool):
        result["phone"] = str(raw_phone).strip()

    updates = raw.get("updates")
    if isinstance(updates, dict):
        result["updates"] = {
            str(k): v.strip() if isinstance(v, str) else v
            for k, v in updates.items()
            if k in UPDATE_FIELDS and isinstance(v, (str, int, float))
        }

    # Enforce non-negotiable identifier rules after LLM extraction.
    if intent in {"UPDATE_USER", "DELETE_USER"}:
        result["email"] = result.get("email") or (
            result["identifier"] if EMAIL_RE.fullmatch(result["identifier"] or "") else None
        )
        result["identifier"] = result["email"]

    if intent == "UPDATE_USER" and result["updates"].get("email") is not None:
        return None
    return result


def llm_parse(text: str) -> dict[str, Any] | None:
    global _last_llm_error
    _last_llm_error = None
    if os.getenv("LLM_ENABLED", "false").lower() != "true":
        _last_llm_error = "LLM_ENABLED is not true"
        return None
    if not os.getenv("OPENAI_API_KEY"):
        _last_llm_error = "OPENAI_API_KEY is missing"
        return None
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=os.getenv("OPENAI_BASE_URL") or None,
        )
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or ""
        action = _sanitize_llm_action(json.loads(content))
        if action is None:
            _last_llm_error = "The LLM returned invalid or unsafe structured output"
        return action
    except Exception as exc:
        # Keep the local parser as the safe fallback, but log the real reason so
        # API-key/model/quota/network problems can be diagnosed during development.
        _last_llm_error = f"{type(exc).__name__}: {exc}"
        logger.exception("OpenAI LLM parser failed: %s", exc)
        return None


def get_llm_status() -> dict[str, Any]:
    enabled = os.getenv("LLM_ENABLED", "false").lower() == "true"
    key_present = bool(os.getenv("OPENAI_API_KEY"))
    return {
        "enabled": enabled,
        "key_present": key_present,
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "base_url": os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1",
        "last_error": _last_llm_error,
    }


def validate_email(email: Any) -> str | None:
    if not isinstance(email, str) or not EMAIL_RE.fullmatch(email.strip()):
        return None
    return email.strip().lower()


def validate_name(name: Any) -> str | None:
    if not isinstance(name, str) or not name.strip():
        return None
    return name.strip()


def validate_phone(phone: Any) -> str | None:
    if phone is None or phone == "":
        return None
    if not isinstance(phone, str):
        return None
    normalized = re.sub(r"[\s().-]", "", phone.strip())
    digits = re.sub(r"\D", "", normalized)
    if not (7 <= len(digits) <= 15):
        return None
    if normalized.startswith("+") and not normalized[1:].isdigit():
        return None
    if not normalized.lstrip("+").isdigit():
        return None
    return phone.strip()


def validate_extra_data(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        return None
    return value.strip()


def add_user(action: dict[str, Any]) -> dict[str, Any]:
    name = validate_name(action.get("name"))
    email = validate_email(action.get("email"))
    if not name:
        return {"message": "Name is required to add a user."}
    if not email:
        return {"message": "The email format is invalid."}

    if find_user_by_email(email):
        return {"message": f"Rejected: A user with email {email} already exists."}

    phone = validate_phone(action.get("phone"))
    if action.get("phone") and phone is None:
        return {"message": "The phone number is invalid."}

    address = action.get("address")
    if address is not None and not isinstance(address, str):
        return {"message": "The address is invalid."}
    extra_data = validate_extra_data(action.get("extra_data"))

    try:
        create_user(name, email, phone, address.strip() if isinstance(address, str) else None, extra_data)
    except Exception as exc:
        # UNIQUE is still enforced at the database level.
        if "UNIQUE constraint failed" in str(exc):
            return {"message": f"Rejected: A user with email {email} already exists."}
        raise

    user = find_user_by_email(email)
    return {"message": f"User {email} was added successfully.", "user": user}


def update_user(action: dict[str, Any]) -> dict[str, Any]:
    email = validate_email(action.get("email") or action.get("identifier"))
    if not email:
        return {"message": "Please provide the user's email. Email is required for update."}

    if not find_user_by_email(email):
        return {"message": "No user exists with that email."}

    updates = action.get("updates") or {}
    # Compatibility with local parser's field/value representation.
    if not updates and action.get("field") and action.get("value") is not None:
        field = action["field"]
        if field == "city":
            field = "address"
        if field == "email":
            return {"message": "Email cannot be changed through the normal update command."}
        updates = {field: action["value"]}

    if not updates:
        return {"message": "Please specify the field and new value to update."}

    clean: dict[str, Any] = {}
    for field, value in updates.items():
        if field == "email":
            return {"message": "Email cannot be changed through the normal update command."}
        if field not in UPDATE_FIELDS:
            return {"message": f"The field '{field}' cannot be updated."}
        if field == "name":
            clean[field] = validate_name(value)
            if not clean[field]:
                return {"message": "The new name is invalid."}
        elif field == "phone":
            clean[field] = validate_phone(value)
            if value and not clean[field]:
                return {"message": "The phone number is invalid."}
        elif field == "address":
            if not isinstance(value, str) or not value.strip():
                return {"message": "The new address is invalid."}
            clean[field] = value.strip()
        elif field == "extra_data":
            clean[field] = validate_extra_data(value)
            if value and clean[field] is None:
                return {"message": "The extra details are invalid."}

    user = update_user_by_email(email, clean)
    return {"message": f"User {email} was updated successfully.", "user": user}


def delete_user(action: dict[str, Any]) -> dict[str, Any]:
    email = validate_email(action.get("email") or action.get("identifier"))
    if not email:
        return {"message": "Please provide the user's email. Email is required for delete."}
    user = delete_user_by_email(email)
    if not user:
        return {"message": "No user exists with that email."}
    return {"message": f"User {email} was deleted."}


def list_users_tool(action: dict[str, Any] | None = None) -> dict[str, Any]:
    users = list_users()
    if not users:
        return {"message": "There are no users in the system yet.", "users": []}
    return {"message": f"Found {len(users)} user(s).", "users": users}


TOOLS = {
    "CREATE_USER": add_user,
    "UPDATE_USER": update_user,
    "DELETE_USER": delete_user,
    "LIST_USERS": list_users_tool,
}


def _merge_actions(local: dict[str, Any], llm: dict[str, Any] | None) -> dict[str, Any]:
    """Merge LLM understanding with deterministic values extracted from the text.

    Values that can be parsed safely from the user's exact message always win. This
    prevents the LLM from changing a phone number, email, or update value while still
    allowing the LLM to understand more conversational wording.
    """
    if not llm:
        return local

    merged = dict(llm)
    if local.get("intent") in VALID_INTENTS and local.get("intent") != "UNKNOWN":
        merged["intent"] = local["intent"]

    for key in ("name", "email", "phone", "address", "extra_data", "identifier"):
        if local.get(key) not in (None, ""):
            merged[key] = local[key]

    local_updates = local.get("updates") or {}
    llm_updates = merged.get("updates") or {}
    merged["updates"] = {**llm_updates, **local_updates}

    # Local parser stores natural-language field/value pairs for UPDATE_USER.
    if local.get("field") and local.get("value") is not None:
        field = "address" if local["field"] == "city" else local["field"]
        if field != "email":
            merged["updates"] = {**merged["updates"], field: local["value"]}

    return merged


def route_command(text: str) -> dict[str, Any]:
    # Always parse the user's exact text locally first. This guarantees that values
    # such as +923321234567 are preserved verbatim. The LLM is then used only to
    # improve intent/field understanding, never to override explicit values.
    local_action = local_parse(text)
    llm_action = llm_parse(text)

    if local_action.get("intent") in TOOLS:
        action = _merge_actions(local_action, llm_action)
        parser = "local+llm" if llm_action is not None else "local"
    elif llm_action is not None:
        action = llm_action
        parser = "llm"
    else:
        action = local_action
        parser = "local"

    intent = action.get("intent", "UNKNOWN")
    if intent not in TOOLS:
        return {
            "message": "I couldn't identify the requested action. "
                       "Please try add, update, delete, or list users."
        }

    result = TOOLS[intent](action)
    result["parser"] = parser
    return result


def process_command(text: str) -> dict[str, Any]:
    return route_command(text)
