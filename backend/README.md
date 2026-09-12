# WPBrigade User Management Agent

Reorganized into the requested backend/frontend structure while preserving the original ChatGPT-style UI and behavior.

## Structure

```text
wpbrigade-user-management/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── crud.py
│   │   ├── tools.py
│   │   ├── chatbot.py
│   │   └── auth.py
│   ├── requirements.txt
│   ├── .env
│   └── README.md
├── frontend/
│   ├── src/
│   │   ├── index.html
│   │   ├── app.js
│   │   └── style.css
│   └── package.json
└── .gitignore
```

## Run

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

The UI is preserved from the supplied project. The frontend is served by FastAPI from `frontend/src`.


## Robust chatbot behavior

- CRUD commands are keyed by the target user's email for update/delete operations.
- Explicit values from the user's message are preserved before LLM interpretation.
- Phone numbers such as `+923321234567` are accepted as text even if an LLM returns them as a JSON number.
- `city` is accepted as a natural-language alias for the existing `address` column.
- After create/update, the API returns the complete saved user record so the UI can immediately use the email-keyed state.

### Run

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API runs on `http://127.0.0.1:8000`. Start the React frontend separately from `frontend` with `npm install` and `npm run dev`.
