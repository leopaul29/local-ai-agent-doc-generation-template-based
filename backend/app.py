"""Local chat agent that fills .docx, .xlsx, .md and .txt templates with an Ollama model."""
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from documents import FORMATS, fill_template, read_template

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:1.7b")
ROOT = Path(__file__).resolve().parent.parent
# shortcut: uploads and outputs are never deleted, add a cleanup if storage/ grows too big
TEMPLATES = ROOT / "storage" / "templates"
OUTPUTS = ROOT / "storage" / "outputs"
TEMPLATE_ID = re.compile(r"[0-9a-f]{32}\.(docx|xlsx|md|txt)")

SYSTEM_PROMPT = """You fill in a document template with the information the user gives you.

Template:
<template>
{template}
</template>

Fields to fill: {fields}

Rules:
- Use only information from the conversation. Never invent names, dates, numbers or other facts.
- You may write longer text fields (summaries, paragraphs) from that information, in the language of the template.
- Set a field to an empty string while its information is unknown.
- In "reply", tell the user briefly what you filled and ask for what is still missing."""

TEMPLATES.mkdir(parents=True, exist_ok=True)
OUTPUTS.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="Doc Agent")


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    template_id: str
    messages: list[Message]


def stored(folder: Path, template_id: str) -> Path:
    path = folder / template_id
    if not TEMPLATE_ID.fullmatch(template_id) or not path.exists():
        raise HTTPException(404, "Unknown template: upload it again.")
    return path


def ask_llm(system: str, messages: list[dict], fields: list[str]) -> dict:
    """Ask Ollama for the field values. The JSON schema forces a {values, reply} answer."""
    schema = {
        "type": "object",
        "properties": {
            "values": {"type": "object", "properties": {f: {"type": "string"} for f in fields}, "required": fields},
            "reply": {"type": "string"},
        },
        "required": ["values", "reply"],
    }
    body = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "system", "content": system}, *messages],
        "format": schema,
        "think": False,  # qwen3 thinks by default: slower, and the schema already shapes the answer
        "stream": False,
        "options": {"num_ctx": 8192},
    }
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            content = json.load(response)["message"]["content"]
    except urllib.error.HTTPError as e:
        raise HTTPException(502, f"Ollama error: {e.read().decode(errors='replace')}")
    except OSError as e:
        raise HTTPException(502, f"Cannot reach Ollama at {OLLAMA_URL} ({getattr(e, 'reason', e)}). Is it running?")
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(502, "The model did not answer valid JSON. Try again or use a bigger model.")


@app.post("/api/templates")
def upload_template(file: UploadFile):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in FORMATS:
        raise HTTPException(400, f"Unsupported file type. Use {', '.join(sorted(FORMATS))}.")
    path = TEMPLATES / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(file.file.read())
    try:
        fields = read_template(path)[1]
        if not fields:
            raise ValueError("no {{ field_name }} placeholder found")
    except Exception as e:  # any parse failure means a bad upload, not a server bug
        path.unlink()
        raise HTTPException(400, f"Cannot use this template: {e}")
    return {"id": path.name, "fields": fields}


@app.post("/api/chat")
def chat(req: ChatRequest):
    src = stored(TEMPLATES, req.template_id)
    text, fields = read_template(src)
    # shortcut: long templates are cut to fit the context of small local models
    system = SYSTEM_PROMPT.format(template=text[:6000], fields=", ".join(fields))
    answer = ask_llm(system, [m.model_dump() for m in req.messages], fields)
    values = {f: str(answer.get("values", {}).get(f) or "") for f in fields}
    fill_template(src, OUTPUTS / src.name, values)
    return {"reply": answer.get("reply", ""), "values": values}


@app.get("/api/download/{template_id}")
def download(template_id: str):
    return FileResponse(stored(OUTPUTS, template_id))


app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run(app, port=8000)
