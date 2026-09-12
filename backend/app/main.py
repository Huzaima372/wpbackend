from pathlib import Path
import os
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .chatbot import get_llm_status, llm_parse, process_command
from .database import init_db, seed_admins
from .auth import authorize, normalize_email
from .schemas import ChatRequest

logger = logging.getLogger(__name__)

BASE_DIR=Path(__file__).resolve().parent
FRONTEND_DIR=BASE_DIR.parent.parent/"frontend"/"src"
load_dotenv(BASE_DIR.parent/".env")

app=FastAPI(title="WPBrigade User Management Agent")
app.mount("/static",StaticFiles(directory=FRONTEND_DIR),name="static")
init_db(); seed_admins()

@app.get("/",response_class=HTMLResponse)
def home(): return (FRONTEND_DIR/"index.html").read_text(encoding="utf-8")

@app.post("/login")
def login(email:str=Form(...)):
    normalized=normalize_email(email)
    if not authorize(normalized):
        return JSONResponse({"ok":False,"message":"This email is not authorized."},status_code=401)
    return {"ok":True,"email":normalized}

@app.post("/chat")
def chat(payload:ChatRequest):
    email=normalize_email(str(payload.email)); message=payload.message.strip()
    if not authorize(email):
        return JSONResponse({"ok":False,"message":"Please log in with an authorized email first."},status_code=401)
    if not message:
        return JSONResponse({"ok":False,"message":"Please enter a command."},status_code=400)
    try:
        return {"ok": True, **process_command(message)}
    except Exception as exc:
        logger.exception("Chat operation failed")
        # Keep the production response safe while making the server-side log useful.
        return JSONResponse({
            "ok": False,
            "message": "The operation could not be completed. Please try again."
        }, status_code=500)

@app.post("/llm-test")
def llm_test():
    action=llm_parse("list users"); status=get_llm_status()
    if action is not None: return {"ok":True,"message":"OpenAI LLM connection is working.","parser":"llm","status":status}
    return JSONResponse({"ok":False,"message":"OpenAI LLM request failed; local fallback remains available.","status":status},status_code=502)

@app.get("/health")
def health():
    enabled=os.getenv("LLM_ENABLED","false").lower()=="true" and bool(os.getenv("OPENAI_API_KEY"))
    return {"status":"ok","llm_enabled":enabled,"model":os.getenv("OPENAI_MODEL","gpt-4o-mini") if enabled else None}
