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

The Vercel deployment is optimized for Vercel serverless hosting and now supports OpenAI as the generative fallback.

- Static Q&A from `Data/static_qa.json` works in Vercel.
- Topic filtering still works.
- If a static FAQ match is not found, the app can call OpenAI for a generated answer.
- Heavy local NLP and BART generation are still disabled by default in Vercel because the required model files and startup cost are not serverless-friendly.

### Vercel environment variables

Add these in your Vercel project settings:

- `OPENAI_API_KEY` = your OpenAI API key
- `OPENAI_MODEL` = `gpt-4o-mini` (recommended default)

Optional:

- `OPENAI_MAX_CONTEXT_ITEMS` = `3`
- `ENABLE_GENERATIVE_MODEL` = `true` only if you still want to try a local BART fallback outside Vercel
- `BART_MODEL_PATH` = path to a local BART model outside Vercel

If you do not add `OPENAI_API_KEY`, the deployed chatbot will still answer direct static FAQ matches, but unmatched questions will return a configuration message instead of a generated response.

If you want a different generative setup in production, use one of these approaches:

1. Connect the app to an external AI API.
2. Host the full ML stack on a VM/container platform instead of Vercel.
3. Provide a compact local model and enable it outside Vercel with:
   - `ENABLE_GENERATIVE_MODEL=true`
   - `BART_MODEL_PATH=<path to local model>`

### Deploy steps

1. Push this repo to GitHub.
2. Import the repo into Vercel.
3. Leave the project root as the repository root.
4. Vercel should detect the Python setup automatically using `vercel.json`.
5. Add the required `OPENAI_API_KEY` environment variable in Vercel.
6. Deploy.

After deploy, test:

- `/`
- `/health`
- `/chat-stream?message=when%20is%20enrollment`
