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
- No business logic changed yet.
