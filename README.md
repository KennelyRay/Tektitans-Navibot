# Tektitans-Navibot
This repository is made to develop a Generative AI Chatbot that answers enrollment related questions for SAMCIS students specially for BSIT and BSCS. 

## Frontend build (React/JSX)

The chat widget and the suggested-prompts row are a small React app (`frontend/src/`), bundled with esbuild into a single static file. The Flask backend and the `/chat-stream` API are untouched by this — it only affects the client-side UI.

- `frontend/src/ChatWidget.jsx` — the chat bubble, message list, SSE streaming, history tracking (ported from the old jQuery `script.js`).
- `frontend/src/StaticQuestionsCarousel.jsx` — the suggested-prompts chip row.
- `frontend/src/main.jsx` — mounts `ChatWidget` into `<div id="navibot-root">` in `templates/index.html`.

To build after changing anything under `frontend/src/`:

```
npm install   # first time only
npm run build
```

This writes `static/js/navibot.bundle.js` and copies it to `api/static/js/navibot.bundle.js` automatically. **Vercel's deploy here is Python-only** (see below) — there is no Node build step in `vercel.json`, so the bundle is a committed build artifact, not something generated at deploy time. Always run `npm run build` and commit the regenerated bundle before deploying frontend changes. `npm run watch` rebuilds on save for local iteration.

### A note on `node_modules` and Vercel

Adding a root-level `package.json` makes Vercel's zero-config detection *want* to run `npm install` during deploy, which would create `node_modules/` (react, react-dom, esbuild's native binary, etc.) in the build container. Since the Python function is configured with `includeFiles: "**/*"`, that could in theory get scooped into the serverless function bundle and blow past Vercel's size limit.

We deliberately do **not** fight this by overriding `installCommand`/`buildCommand` in `vercel.json` — an earlier attempt at that caused the Python function to crash outright (`FUNCTION_INVOCATION_FAILED`), most likely because it also interfered with Vercel's own `requirements.txt` install step for the Python runtime, which happens before `from flask import Flask` at the top of `api/index.py` can even succeed. Overriding root-level build commands for a Python-runtime function is risky and not worth it here.

Instead, `node_modules/`, `frontend/`, `package.json`, `package-lock.json`, and `build.mjs` are excluded via `.vercelignore`, which is the safer, narrower fix — it keeps those paths out of the deployment without touching how the Python function itself gets built. If you ever see function bloat or crashes again after touching `vercel.json`, check that no `installCommand`/`buildCommand` override crept back in.

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
