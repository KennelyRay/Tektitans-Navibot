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
- Runtime evidence collected locally with instrumented Flask test-client requests.
- Root cause confirmed for wrong static answers in history-sensitive enrollment questions.
- Minimal fix applied; awaiting deployed user verification.

## Evidence Summary
- Pre-fix evidence showed `How do I enroll?` over-matching the wrong FAQ because single-token overlap produced a perfect score and broad venue variants captured generic enrollment prompts.
- Additional pre-fix evidence showed that with existing venue history, `How do I enroll?` was rewritten by the follow-up resolver into the venue FAQ instead of the enrollment-process FAQ.
- Post-fix evidence shows `How do I enroll?` now resolves to `How do I start the enrollment process?` even when prior venue history exists.

## Fix Summary
- Tightened static similarity scoring so overlap does not get a perfect score from single-token matches.
- Moved the broad `where is the enrollment venue` phrase to the combined venue FAQ target.
- Added explicit enrollment-process variants to the enrollment-process FAQ target.
- Added a higher-priority `enrollment_process` topic so `How do I enroll?` is not hijacked by venue follow-up history.
