# local-ai-agent-doc-generation-template-based

Chat with a local AI model to fill a document template. Upload a `.docx`, `.xlsx`, `.md` or `.txt`
file with `{{ field_name }}` placeholders, give the information in the chat, and download the
filled document in the same format. Everything runs on your machine with [Ollama](https://ollama.com).

## Run

1. Install [Ollama](https://ollama.com/download) (0.5 or later) and pull a model:
   ```bash
   ollama pull llama3.2
   ```
2. Install the backend and start it (Python 3.10+):
   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r backend/requirements.txt
   python backend/app.py
   ```
3. Open http://localhost:8000.

Environment variables: `OLLAMA_MODEL` picks another model (a bigger one writes better text),
`OLLAMA_URL` points to another Ollama server (default `http://localhost:11434`).

## Templates

Put a placeholder where each value goes. Names use letters, digits and underscores.

```markdown
# Proposal for {{ client_name }}

Date: {{ date }}

{{ summary }}
```

- **Word**: placeholders work in paragraphs, tables, headers and footers. Styles are kept.
- **Excel**: placeholders work in any cell of any sheet. Styles and formulas are kept.
  Values are written as text.
- **Markdown / text**: UTF-8 files.

The agent fills each field from the conversation, writes longer fields (like `summary`) from what
you said, and asks for what is missing. Each answer regenerates the document, and the download
button always gives the latest version. Templates use [Jinja](https://jinja.palletsprojects.com/)
syntax, so `{% if field %}…{% endif %}` also works.

## How it works

| Path | Role |
|---|---|
| `frontend/index.html` | Chat UI: plain HTML and JavaScript, no build step |
| `backend/app.py` | FastAPI server: upload, chat and download routes; calls Ollama |
| `backend/documents.py` | Finds and fills the placeholders of each format |

The browser keeps the conversation and sends all of it on each turn, so the server stores only
files (`storage/`). The server sends the template text, the field names and the conversation to
Ollama, and a JSON schema forces the answer into `{"values": {...}, "reply": "..."}`. The
values fill the template; the reply goes back to the chat.

## Tests

```bash
pip install pytest httpx2
pytest backend
```
