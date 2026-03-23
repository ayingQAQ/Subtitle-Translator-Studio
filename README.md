# Subtitle Translator Studio (MVP)

Local single-user subtitle translator for **existing subtitle files only**.
No video extraction, no OCR, no container demux.

This is a **local web app**:
- Start with Python
- Use in browser at `http://localhost:8501`

## Features

- Translate existing subtitles between Japanese, Chinese, and English
- Local web UI (Streamlit)
- Official support: `SRT`, `ASS`, `SSA`, `VTT`
- Best-effort support: `SUB (MicroDVD)`, `MPL2`, `TMP`, `TTML`, `SAMI`
- Encoding-safe pipeline with fallback to `UTF-8 BOM` when needed
- Optional glossary import (`CSV`)
- Local translation memory (`sqlite3`)
- Multi-provider support:
  - `Google Translate API`
  - `Google Translate Web (Unofficial, no key)`
  - `DeepL API`
  - `OpenAI`
  - `Google Gemini (OpenAI-compatible)`
  - `DeepSeek`
  - `Qwen / DashScope`
  - `Zhipu GLM`
  - Custom `OpenAI-compatible` endpoint
- Sidebar **Test API Connection** button to verify key + endpoint before translating

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

## Run

1. Install dependencies:

```powershell
uv sync --all-groups
```

2. Prepare env file:

```powershell
Copy-Item .env.example .env
```

3. Fill at least one provider key in `.env`:

- `DEEPSEEK_API_KEY`
- or `OPENAI_API_KEY`
- or `GOOGLE_TRANSLATE_API_KEY`
- or `DEEPL_API_KEY`
- or `GEMINI_API_KEY`
- or `DASHSCOPE_API_KEY`
- or `ZHIPU_API_KEY`

Or use `Google Translate Web (Unofficial)` preset without key.

4. Start app:

```powershell
uv run streamlit run app.py
```

5. Open:

`http://localhost:8501`

## Glossary Format

CSV header must be:

```csv
source,target,notes
subtitle,subtitle,UI term
sister,sister,dialog context
```

## Test

```powershell
uv run pytest
```
