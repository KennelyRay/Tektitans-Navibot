# Tektitans-Navibot
This repository is made to develop a Generative AI Chatbot that answers enrollment related questions for SAMCIS students specially for BSIT and BSCS. 

## Deploying on Vercel

This repo is now configured to deploy as a Python serverless app on Vercel.

### Included deployment files

- `api/index.py` exposes the Flask `app` for Vercel.
- `vercel.json` routes all requests to the Flask app.
- `requirements.txt` installs the minimal runtime dependency set.
- `.vercelignore` excludes training artifacts and large local model folders from the upload.

### Important runtime behavior

The Vercel deployment is optimized for Vercel serverless hosting and uses Groq (free tier, OpenAI-compatible API) as the generative engine.

- Only an exact match against a known question in `Data/static_qa.json` is answered directly from the static file (fast, deterministic, always correct).
- Every other enrollment question is answered by Groq, grounded with the *entire* static FAQ set as reference context plus the real conversation history, so it can resolve follow-up questions ("what about for irregular students?") correctly instead of relying on hand-written keyword/topic rewrite rules.
- A small keyword list (`Data/non_academic_contexts.json`) still screens out obviously unrelated topics (movies, food, other schools, etc.) before calling Groq.
- Heavy local NLP and BART generation are still disabled by default in Vercel because the required model files and startup cost are not serverless-friendly.
- The Groq call is a plain HTTP request (`urllib`, no extra SDK dependency) to `https://api.groq.com/openai/v1/chat/completions` with `stream: true`.

### Vercel environment variables

Add these in your Vercel project settings:

- `GROQ_API_KEY` = your free API key from [console.groq.com](https://console.groq.com/keys)
- `GROQ_MODEL` = `llama-3.3-70b-versatile` (recommended default)

Optional:

- `GROQ_MAX_TOKENS` = `300`
- `ENABLE_GENERATIVE_MODEL` = `true` only if you still want to try a local BART fallback outside Vercel
- `BART_MODEL_PATH` = path to a local BART model outside Vercel

If you do not add `GROQ_API_KEY`, the deployed chatbot will still answer direct static FAQ matches, but unmatched questions will return a configuration message instead of a generated response.

Groq's free tier requires no credit card and no spend — it's rate-limited per minute/day rather than metered by cost.

If you want a different generative setup in production, use one of these approaches:

1. Connect the app to a different external AI API.
2. Host the full ML stack on a VM/container platform instead of Vercel.
3. Provide a compact local model and enable it outside Vercel with:
   - `ENABLE_GENERATIVE_MODEL=true`
   - `BART_MODEL_PATH=<path to local model>`

### Deploy steps

1. Push this repo to GitHub.
2. Import the repo into Vercel.
3. Leave the project root as the repository root.
4. Vercel should detect the Python setup automatically using `vercel.json`.
5. Add the required `GROQ_API_KEY` environment variable in Vercel.
6. Deploy.

After deploy, test:

- `/`
- `/health`
- `/chat-stream?message=when%20is%20enrollment`
