# Debug Session: vercel-function-crash [OPEN]

## Symptom
- Vercel deploy succeeds, but the serverless function crashes with `500: INTERNAL_SERVER_ERROR`.
- The browser shows `FUNCTION_INVOCATION_FAILED`.

## Scope
- Affects the deployed Vercel serverless function.
- Exact failing route is not yet confirmed, but the screenshot shows `/favicon.ico` also returning 500.

## Hypotheses
1. `api/index.py` fails while importing `Bart_Bot`.
2. A required dependency is missing in the Vercel runtime.
3. Startup code in `Bart_Bot.py` crashes while reading files or env vars.
4. The deployed Python path does not resolve `Bart_Bot` from `api/index.py`.
5. An exception occurs before Flask routing starts, so Vercel only shows a generic crash page.

## Evidence Plan
- Add startup instrumentation in `api/index.py` only.
- Capture import/bootstrap exception details in the HTTP response for debugging.
- Verify whether the crash is import-time or route-time.

## Status
- Session opened.
- Evidence received from Vercel build logs.
- Confirmed root cause: Vercel builder could not statically find a top-level `app`, `application`, or `handler` symbol in `api/index.py`.
- Minimal fix applied: declared `app = Flask(__name__)` at module top level so Vercel can detect the entrypoint, while preserving bootstrap instrumentation.
- Runtime evidence received from deployed traceback.
- Confirmed secondary root cause: the deployed Python function bundle did not include `Data/static_qa.json`, causing `FileNotFoundError` during `load_config()`.
- Minimal fix applied: replaced legacy `builds` config with `functions` config and explicitly included `Data/**`, `templates/**`, and `static/**` in the Python function bundle.
- Additional build evidence received from Vercel.
- Confirmed tertiary root cause: `functions.api/index.py.runtime` used an invalid value for built-in Python functions.
- Minimal fix applied: removed the invalid `runtime` field and kept `includeFiles` only.
- Additional runtime evidence received from deployed traceback after redeploy.
- Observed that the narrower `includeFiles` pattern still did not place `Data/static_qa.json` into the function bundle.
- Minimal fix applied: broadened `includeFiles` to `**/*`, relying on `.vercelignore` to keep heavy artifacts out while ensuring required runtime assets are bundled.
- Additional runtime evidence received from deployed traceback after broader include.
- Confirmed that Vercel still did not expose the root-level `Data` directory to the running function at `/var/task/Data/...`.
- Minimal fix applied: mirrored required runtime assets under `api/` and updated `Bart_Bot.py` to fall back to `api/Data`, `api/templates`, and `api/static` when root-level assets are unavailable.
