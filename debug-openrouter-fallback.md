# Debug Session: openrouter-fallback [OPEN]

## Symptom
- OpenRouter environment variables have been configured.
- The chatbot still reports a fallback response instead of using OpenRouter.

## Scope
- Affects the deployed chat generation path for unmatched enrollment questions.
- Static FAQ answers may still work correctly.

## Hypotheses
1. `OPENROUTER_API_KEY` is missing at runtime in Vercel.
2. `OPENROUTER_MODEL` is invalid or unavailable for the configured account.
3. The OpenRouter request fails due to headers or request-shape incompatibility.
4. The frontend only exposes `fallback` source and hides the actual fallback reason.
5. The deployment is serving stale code or stale environment variables.

## Evidence Plan
- Add minimal instrumentation to expose fallback reason and runtime provider state.
- Reproduce with one unmatched chat question.
- Compare the observed fallback reason against the hypotheses.

## Status
- Session opened.
- No business logic changes yet.
