from html import escape
from pathlib import Path
import json
import os
import re
import time
import urllib.error
import urllib.request

from flask import Flask, Response, render_template, request, send_from_directory, stream_with_context


BASE_DIR = Path(__file__).resolve().parent
API_DIR = BASE_DIR / "api"


def resolve_runtime_dir(directory_name):
    candidates = [
        BASE_DIR / directory_name,
        API_DIR / directory_name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


DATA_DIR = resolve_runtime_dir("Data")
TEMPLATES_DIR = resolve_runtime_dir("templates")
STATIC_DIR = resolve_runtime_dir("static")
FINE_TUNED_BART_DIR = BASE_DIR / "output" / "fine-tuned-bart"
IS_VERCEL = bool(os.environ.get("VERCEL")) or bool(os.environ.get("VERCEL_ENV"))
ENABLE_GENERATIVE_MODEL = os.environ.get("ENABLE_GENERATIVE_MODEL", "").lower() in {"1", "true", "yes"} and not IS_VERCEL
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip() or "llama-3.3-70b-versatile"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
BART_WEIGHT_FILES = ("pytorch_model.bin", "model.safetensors", "tf_model.h5")
QUESTION_WORDS = {"how", "who", "what", "where", "when", "why", "which"}
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "for", "from", "how",
    "i", "in", "is", "it", "my", "of", "on", "or", "please", "the", "to", "was",
    "what", "when", "where", "which", "who", "why", "with", "you", "your",
}


def get_env_int(name, default):
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


GROQ_MAX_TOKENS = get_env_int("GROQ_MAX_TOKENS", 300)

app = Flask(
    __name__,
    template_folder=str(TEMPLATES_DIR),
    static_folder=str(STATIC_DIR),
)


def load_json(file_path):
    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_config():
    """Load the chatbot data files."""
    static_qa = load_json(DATA_DIR / "static_qa.json")
    non_academic_contexts = load_json(DATA_DIR / "non_academic_contexts.json")
    return static_qa, non_academic_contexts.get("contexts", {})


STATIC_QA, NON_ACADEMIC_CONTEXTS = load_config()
static_questions = list(STATIC_QA.keys())


def normalize_question(text):
    return re.sub(r"\s+", " ", text.strip().lower()).rstrip("?.! ")


STATIC_QUESTIONS_BY_NORMALIZED_TEXT = {
    normalize_question(question): question for question in static_questions
}


def build_faq_reference_block():
    """Render the full FAQ set as grounding context for the generative model.

    The dataset is small enough (a few dozen entries) to pass in full, which
    avoids the keyword/similarity scoring that used to pick the wrong FAQ.
    """
    return "\n\n".join(f"Q: {question}\nA: {answer}" for question, answer in STATIC_QA.items())


FAQ_REFERENCE_BLOCK = build_faq_reference_block()

generation_model = None
generation_tokenizer = None
generation_model_checked = False
llm_client = None
llm_client_checked = False


def tokenize_text(text):
    return re.findall(r"[a-z0-9']+", text.lower())


def preprocess_query(query):
    """Normalize a query without relying on runtime downloads."""
    filtered_words = [word for word in tokenize_text(query) if word not in STOP_WORDS]
    return {
        "processed_text": " ".join(filtered_words),
        "tokens": set(filtered_words),
    }


def parse_history_param(raw_history):
    if not raw_history:
        return []

    try:
        parsed = json.loads(raw_history)
    except json.JSONDecodeError:
        return []

    if not isinstance(parsed, list):
        return []

    history = []
    for item in parsed[-6:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip().lower()
        text = str(item.get("text", "")).strip()
        if role in {"user", "bot"} and text:
            history.append({"role": role, "text": text})
    return history


def resolve_existing_path(*candidates):
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return path
    return None


def has_bart_weights(model_path):
    return any((model_path / file_name).exists() for file_name in BART_WEIGHT_FILES)


def get_generation_model():
    global generation_model
    global generation_tokenizer
    global generation_model_checked

    if generation_model_checked:
        return generation_model, generation_tokenizer

    generation_model_checked = True
    if not ENABLE_GENERATIVE_MODEL:
        return None, None

    model_path = resolve_existing_path(os.environ.get("BART_MODEL_PATH"), FINE_TUNED_BART_DIR)
    if not model_path or not has_bart_weights(model_path):
        print("Generative model disabled: no local BART weights were found.")
        return None, None

    try:
        from transformers import BartForConditionalGeneration, BartTokenizer

        generation_model = BartForConditionalGeneration.from_pretrained(
            str(model_path),
            local_files_only=True,
        )
        generation_tokenizer = BartTokenizer.from_pretrained(
            str(model_path),
            local_files_only=True,
        )
    except Exception as exc:
        print(f"Unable to load generative model: {exc}")
        generation_model = None
        generation_tokenizer = None

    return generation_model, generation_tokenizer


def get_llm_client():
    global llm_client
    global llm_client_checked

    if llm_client_checked:
        return llm_client

    llm_client_checked = True
    llm_client = bool(GROQ_API_KEY)
    return llm_client


def check_non_academic_context(query_tokens):
    """Check if query contains non-academic context terms."""
    for context, terms in NON_ACADEMIC_CONTEXTS.items():
        normalized_terms = {term.lower() for term in terms}
        matched_terms = query_tokens & normalized_terms
        if matched_terms:
            return {
                "has_non_academic": True,
                "context": context,
                "matched_terms": matched_terms,
            }

    return {
        "has_non_academic": False,
        "context": None,
        "matched_terms": set(),
    }


def check_relevancy(query):
    """Reject queries that are clearly about an unrelated topic (movies, food, other schools, etc.).

    Anything that isn't an obvious off-topic term is left for the generative
    model to judge, since its system prompt already restricts it to
    enrollment topics and it understands intent far better than a keyword list.
    """
    query_tokens = preprocess_query(query)["tokens"]
    non_academic_check = check_non_academic_context(query_tokens)
    if non_academic_check["has_non_academic"]:
        return {
            "is_relevant": False,
            "reason": f"{non_academic_check['context']}-related terms: {', '.join(sorted(non_academic_check['matched_terms']))}",
        }

    return {"is_relevant": True}


def find_static_answer(query):
    """Return a static FAQ answer only for an exact (whitespace/case/punctuation
    insensitive) match against a known question.

    Fuzzy/keyword similarity scoring used to pick the wrong FAQ entry for
    related-but-different questions (e.g. "How do I enroll?" being hijacked by
    venue follow-up history). Requiring an exact match removes that failure
    mode entirely; anything else is answered by the grounded generative model.
    """
    matched_question = STATIC_QUESTIONS_BY_NORMALIZED_TEXT.get(normalize_question(query))
    if matched_question:
        return {
            "found": True,
            "answer": STATIC_QA[matched_question],
            "matched_question": matched_question,
        }

    return {"found": False}


def process_query(query):
    """Check relevancy, then exact static answers, then generative fallback."""
    relevancy_result = check_relevancy(query)
    if not relevancy_result["is_relevant"]:
        message = (
            "I can only help with enrollment-related questions. "
            f"Your question appears to contain {relevancy_result['reason']}."
        )
        return {
            "status": "not_relevant",
            "message": message,
        }

    static_result = find_static_answer(query)
    if static_result["found"]:
        return {
            "status": "static_answer",
            "message": static_result["answer"],
        }

    return {
        "status": "use_generation",
        "message": None,
    }


def contains_multiple_questions(query):
    query_words = query.lower().split()
    question_count = sum(1 for word in query_words if word in QUESTION_WORDS)
    return question_count >= 2


def format_response(response_text, escape_html=True):
    """Wrap plain text into the chatbot's list/paragraph HTML.

    Static FAQ answers intentionally embed trusted `<a href="mailto:...">`
    links authored in `static_qa.json`, so they're rendered with
    escape_html=False. Generated (Groq) text is untrusted and always escaped
    to avoid rendering injected markup.
    """
    if escape_html:
        response_text = escape(response_text, quote=False)
    formatted_text = "<div class='chatbot-response'>"
    in_numbered_list = False
    in_bullet_list = False

    placeholders = {}

    def stash(html):
        placeholder_id = f"__HTML_{len(placeholders)}__"
        placeholders[placeholder_id] = html
        return placeholder_id

    # Protect any pre-formed <a>...</a> tags (e.g. trusted mailto links from
    # static_qa.json) before the rules below run, since the colon->br rule
    # would otherwise break a "mailto:" attribute value across a line.
    response_text = re.sub(
        r"<a\b[^>]*>.*?</a>",
        lambda match: stash(match.group(0)),
        response_text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    def add_www(match):
        url = match.group(1)
        if not url.startswith("www.") and not url.startswith("https://www.") and not url.startswith("http://www."):
            url = re.sub(r"(https?://)", r"\1www.", url)
        return f"<a href='{url}'>{url}</a>"

    url_pattern = r"(http[s]?://[^\s<]+)"
    response_text = re.sub(url_pattern, lambda match: stash(add_www(match)), response_text)

    def insert_br_outside_url(text):
        pattern = r"(?<!http:)(?<!https:):(?!\d)"
        return re.sub(pattern, r":<br>", text)

    response_text = insert_br_outside_url(response_text)

    for placeholder_id, html in placeholders.items():
        response_text = response_text.replace(placeholder_id, html)

    lines = response_text.splitlines()
    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith("1. "):
            if not in_numbered_list:
                if in_bullet_list:
                    formatted_text += "</ul>"
                    in_bullet_list = False
                formatted_text += "<ol>"
                in_numbered_list = True
            formatted_text += f"<li>{stripped_line[3:].strip()}</li>"
        elif stripped_line.startswith("- "):
            if in_numbered_list:
                formatted_text += "</ol>"
                in_numbered_list = False
            if not in_bullet_list:
                formatted_text += "<ul>"
                in_bullet_list = True
            formatted_text += f"<li>{stripped_line[2:].strip()}</li>"
        elif stripped_line == "":
            if in_numbered_list:
                formatted_text += "</ol>"
                in_numbered_list = False
            if in_bullet_list:
                formatted_text += "</ul>"
                in_bullet_list = False
            formatted_text += "<br>"
        else:
            if in_numbered_list:
                formatted_text += "</ol>"
                in_numbered_list = False
            if in_bullet_list:
                formatted_text += "</ul>"
                in_bullet_list = False
            formatted_text += f"<p>{stripped_line}</p>"

    if in_numbered_list:
        formatted_text += "</ol>"
    if in_bullet_list:
        formatted_text += "</ul>"

    formatted_text += "</div>"
    return formatted_text


def split_into_safe_chunks(text):
    return re.findall(r"[^.!?]+[.!?]?", text, re.DOTALL)


def build_meta_event(**payload):
    return f"event: meta\ndata: {json.dumps(payload)}\n\n"


def reveal_text_progressively(text, words_per_chunk=3, delay=0.03):
    """Yield the text growing a few words at a time, preserving line breaks.

    Static/guard replies used to appear all at once while Groq answers
    streamed in, which made the bot feel inconsistent. Revealing every reply
    the same gradual way makes the whole chat feel live.
    """
    lines = text.split("\n")
    revealed_lines = []
    for line in lines:
        words = line.split(" ")
        for end in range(words_per_chunk, len(words), words_per_chunk):
            yield "\n".join(revealed_lines + [" ".join(words[:end])])
            time.sleep(delay)
        revealed_lines.append(line)
        yield "\n".join(revealed_lines)
        time.sleep(delay)


def stream_quick_message(text, source, escape_html=True):
    """Stream an already-known reply (static FAQ answer, guard message, etc.)
    with the same gradual reveal as a generated answer, instead of dumping it
    in one instant chunk."""
    yield build_meta_event(source=source)
    for partial_text in reveal_text_progressively(text):
        yield format_response(partial_text, escape_html=escape_html)
    yield "[END]"


def deployed_fallback_message():
    return (
        "I can answer common enrollment questions, but the AI response service is not configured yet. "
        "Add GROQ_API_KEY in Vercel environment variables to enable generated answers."
    )


def temporary_service_message():
    return (
        "I can help with enrollment questions, but the live response service is temporarily unavailable. "
        "Please try again in a moment or ask one of the suggested questions below."
    )


def build_groq_messages(prompt, history):
    """Convert stored {role: user|bot, text} turns into OpenAI-style chat messages.

    Passing real history lets the model resolve follow-ups ("what about for
    irregular students?") from actual conversational context instead of a
    hand-written set of topic-rewrite rules.
    """
    messages = [{"role": "system", "content": GROQ_SYSTEM_PROMPT}]
    for entry in history:
        role = "user" if entry["role"] == "user" else "assistant"
        messages.append({"role": role, "content": entry["text"]})
    messages.append({"role": "user", "content": prompt})
    return messages


GROQ_SYSTEM_PROMPT = (
    "You are NaviBot, a helpful enrollment assistant for SAMCIS students, especially BSIT and BSCS. "
    "Answer only enrollment-related, registration-related, scheduling, tuition, requirements, and academic process questions. "
    "If the user asks about unrelated topics, politely refuse and redirect them to enrollment concerns. "
    "Ground every answer strictly in the FAQ reference below. If the reference does not cover the question, "
    "say you are not certain and recommend the student contact the department or check the SLU SAMCIS Facebook "
    "page, instead of guessing or inventing details. "
    "Use the conversation history to correctly interpret follow-up questions, "
    "e.g. 'what about for irregular students?' refers back to whatever the previous answer was about. "
    "Keep responses concise, clear, and student-friendly. When listing steps, use numbered or bulleted formatting.\n\n"
    f"FAQ reference:\n{FAQ_REFERENCE_BLOCK}"
)


def stream_groq_response(prompt, history):
    if not GROQ_API_KEY:
        yield build_meta_event(
            source="fallback",
            reason="missing_groq_key",
            groq_key_present=bool(GROQ_API_KEY),
            groq_model=GROQ_MODEL,
        )
        for partial_text in reveal_text_progressively(deployed_fallback_message()):
            yield format_response(partial_text)
        yield "[END]"
        return

    payload = json.dumps(
        {
            "model": GROQ_MODEL,
            "messages": build_groq_messages(prompt, history),
            "temperature": 0.2,
            "max_tokens": GROQ_MAX_TOKENS,
            "stream": True,
        }
    ).encode("utf-8")

    http_request = urllib.request.Request(
        GROQ_API_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
    )

    try:
        accumulated_response = ""
        sent_source_meta = False
        with urllib.request.urlopen(http_request, timeout=30) as http_response:
            for raw_line in http_response:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue

                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break

                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if not delta:
                    continue

                if not sent_source_meta:
                    yield build_meta_event(
                        source="groq",
                        model=GROQ_MODEL,
                        max_tokens=GROQ_MAX_TOKENS,
                    )
                    sent_source_meta = True

                accumulated_response += delta
                yield format_response(accumulated_response)
    except Exception as exc:
        yield build_meta_event(
            source="fallback",
            reason="groq_error",
            groq_model=GROQ_MODEL,
            error=str(exc)[:300],
        )
        for partial_text in reveal_text_progressively(temporary_service_message()):
            yield format_response(partial_text)
    yield "[END]"


def generate_response_stream(prompt, history):
    llm_enabled = bool(get_llm_client())
    if llm_enabled:
        for chunk in stream_groq_response(prompt, history):
            yield chunk
        return

    model, tokenizer = get_generation_model()
    if not model or not tokenizer:
        for partial_text in reveal_text_progressively(deployed_fallback_message()):
            yield format_response(partial_text)
        yield "[END]"
        return

    inputs = tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=512,
        padding="max_length",
    )
    outputs = model.generate(
        input_ids=inputs["input_ids"],
        attention_mask=inputs["attention_mask"],
        max_length=512,
        num_beams=7,
        early_stopping=True,
    )

    response = tokenizer.decode(outputs[0], skip_special_tokens=True)
    accumulated_response = ""
    for token in split_into_safe_chunks(response):
        accumulated_response += token
        yield format_response(accumulated_response)
        time.sleep(0.05)
    yield "[END]"


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/health")
def health():
    return {
        "status": "ok",
        "generative_model_enabled": ENABLE_GENERATIVE_MODEL,
        "groq_enabled": bool(GROQ_API_KEY),
        "groq_key_present": bool(GROQ_API_KEY),
        "groq_model": GROQ_MODEL,
        "groq_max_tokens": GROQ_MAX_TOKENS,
        "vercel": IS_VERCEL,
    }


@app.route("/Data/static_qa.json")
def serve_qa_json():
    return send_from_directory(str(DATA_DIR), "static_qa.json")


def emit_sse_frames(stream):
    for chunk in stream:
        if chunk == "[END]":
            yield "data: [END]\n\n"
        elif chunk.startswith("event: meta\n"):
            yield chunk
        else:
            yield f"data: {chunk}\n\n"


@app.route("/chat-stream")
def chat_stream():
    user_input = request.args.get("message", "").strip()
    history = parse_history_param(request.args.get("history", ""))
    if not user_input:
        return Response("No message provided.", status=400)

    def generate():
        try:
            if contains_multiple_questions(user_input):
                yield from emit_sse_frames(
                    stream_quick_message("Please ask one question at a time.", source="multi_question_guard")
                )
                return

            if user_input.lower() == "thank you":
                yield from emit_sse_frames(
                    stream_quick_message("No worries! Happy to help!", source="small_talk")
                )
                return

            result = process_query(user_input)

            if result["status"] == "not_relevant":
                yield from emit_sse_frames(
                    stream_quick_message(result["message"], source="relevancy_guard")
                )
                return

            if result["status"] == "static_answer":
                yield from emit_sse_frames(
                    stream_quick_message(result["message"], source="static_qa", escape_html=False)
                )
                return

            yield from emit_sse_frames(generate_response_stream(user_input, history))
        except Exception as exc:
            print(f"Error in generate(): {exc}")
            yield from emit_sse_frames(
                stream_quick_message(temporary_service_message(), source="fallback")
            )

    response = Response(stream_with_context(generate()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


if __name__ == "__main__":
    try:
        from gevent.pywsgi import WSGIServer

        print("Starting Flask application with Gevent WSGI server...")
        http_server = WSGIServer(("0.0.0.0", 5000), app)
        http_server.serve_forever()
    except Exception:
        print("Starting Flask development server...")
        app.run(host="0.0.0.0", port=5000)
