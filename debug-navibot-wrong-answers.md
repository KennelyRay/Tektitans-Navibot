# Debug Session: navibot-wrong-answers [OPEN]

## Symptom
- The generative AI path is not working properly.
- Some static questions are returning the wrong answers.

## Scope
- Affects Navibot answer selection and response quality.
- May involve static FAQ matching, follow-up interpretation, frontend history payloads, or Gemini fallback behavior.

## Hypotheses
1. The follow-up resolver rewrites non-follow-up questions into the wrong FAQ target.
2. The FAQ similarity matching is overly permissive and chooses the wrong static answer.
3. The frontend sends stale history, causing the backend to misinterpret normal questions as follow-ups.
4. The Gemini path is being used when a static FAQ should have answered first.
5. The deployed runtime is serving stale or unsynced assets/code compared with the current source tree.

## Evidence Plan
- Add instrumentation to the request flow, follow-up resolution, FAQ matching, and generation selection.
- Reproduce with a few known-good and known-bad questions.
- Compare the runtime logs to confirm which branch is producing the wrong answer.

## Status
- Session opened.
- Instrumentation pending.
