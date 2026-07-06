from difflib import SequenceMatcher
from pathlib import Path
from html import escape
import json
import os
import re
import time

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
ENABLE_SEMANTIC_MODELS = os.environ.get("ENABLE_SEMANTIC_MODELS", "").lower() in {"1", "true", "yes"} and not IS_VERCEL
ENABLE_GENERATIVE_MODEL = os.environ.get("ENABLE_GENERATIVE_MODEL", "").lower() in {"1", "true", "yes"} and not IS_VERCEL
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip() or "openai/gpt-4o-mini"
OPENROUTER_SITE_URL = os.environ.get("OPENROUTER_SITE_URL", "").strip()
OPENROUTER_APP_NAME = os.environ.get("OPENROUTER_APP_NAME", "Tektitans-Navibot").strip() or "Tektitans-Navibot"
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


OPENROUTER_MAX_CONTEXT_ITEMS = get_env_int("OPENROUTER_MAX_CONTEXT_ITEMS", 3)
OPENROUTER_MAX_TOKENS = get_env_int("OPENROUTER_MAX_TOKENS", 300)

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
    topics_data = load_json(DATA_DIR / "topics.json")
    non_academic_contexts = load_json(DATA_DIR / "non_academic_contexts.json")
    return static_qa, topics_data.get("topics", []), non_academic_contexts.get("contexts", {})


STATIC_QA, enrollment_topics, NON_ACADEMIC_CONTEXTS = load_config()
static_questions = list(STATIC_QA.keys())

sentence_model = None
sentence_util = None
sentence_model_checked = False
semantic_embeddings_ready = False
static_embeddings = None
topic_embeddings = None
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


def get_sentence_model():
    global sentence_model
    global sentence_util
    global sentence_model_checked

    if sentence_model_checked:
        return sentence_model, sentence_util

    sentence_model_checked = True
    if not ENABLE_SEMANTIC_MODELS:
        return None, None

    model_path = resolve_existing_path(os.environ.get("SENTENCE_MODEL_PATH"))
    if not model_path:
        print("Semantic model disabled: SENTENCE_MODEL_PATH is not configured.")
        return None, None

    try:
        from sentence_transformers import SentenceTransformer, util

        sentence_model = SentenceTransformer(str(model_path))
        sentence_util = util
    except Exception as exc:
        print(f"Unable to load sentence model: {exc}")
        sentence_model = None
        sentence_util = None

    return sentence_model, sentence_util


def ensure_semantic_embeddings():
    global semantic_embeddings_ready
    global static_embeddings
    global topic_embeddings

    if semantic_embeddings_ready:
        return static_embeddings is not None and topic_embeddings is not None

    semantic_embeddings_ready = True
    model, _ = get_sentence_model()
    if not model:
        return False

    static_embeddings = model.encode(static_questions, convert_to_tensor=True)
    topic_embeddings = model.encode(enrollment_topics, convert_to_tensor=True)
    return True


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
    if not OPENROUTER_API_KEY:
        return None

    try:
        from openai import OpenAI

        llm_client = OpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )
    except Exception as exc:
        print(f"Unable to initialize OpenRouter client: {exc}")
        llm_client = None

    return llm_client


def question_similarity_score(query, query_tokens, question):
    question_lower = question.lower().strip()
    question_tokens = set(tokenize_text(question_lower)) - STOP_WORDS
    overlap_score = len(query_tokens & question_tokens) / max(len(question_tokens), 1)
    sequence_score = SequenceMatcher(None, query.lower().strip(), question_lower).ratio()
    substring_score = 1.0 if query.lower().strip() in question_lower or question_lower in query.lower().strip() else 0.0
    return max(overlap_score, sequence_score, substring_score)


def best_static_question_score(query, query_tokens):
    best_question = None
    best_score = 0.0

    for question in static_questions:
        score = question_similarity_score(query, query_tokens, question)
        if score > best_score:
            best_score = score
            best_question = question

    return best_question, best_score


def get_top_static_matches(query, limit=3):
    processed = preprocess_query(query)
    query_tokens = processed["tokens"]
    ranked_matches = []

    for question in static_questions:
        score = question_similarity_score(query, query_tokens, question)
        ranked_matches.append((score, question))

    ranked_matches.sort(key=lambda item: item[0], reverse=True)
    return ranked_matches[:limit]


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


def check_relevancy(query, threshold=0.5):
    """Check whether a query is related to enrollment topics."""
    processed = preprocess_query(query)
    query_text = processed["processed_text"]
    query_tokens = processed["tokens"]

    non_academic_check = check_non_academic_context(query_tokens)
    if non_academic_check["has_non_academic"]:
        return {
            "is_relevant": False,
            "confidence_score": 0,
            "reason": f"Query contains {non_academic_check['context']}-related terms: {', '.join(sorted(non_academic_check['matched_terms']))}",
        }

    matching_topics = {
        topic for topic in enrollment_topics
        if topic.lower() in query_text or topic.lower() in query_tokens
    }
    academic_ratio = len(matching_topics) / max(len(query_tokens), 1)
    _, best_keyword_score = best_static_question_score(query, query_tokens)

    max_score = best_keyword_score
    if ensure_semantic_embeddings():
        model, util = get_sentence_model()
        query_embedding = model.encode(query_text or query, convert_to_tensor=True)
        topic_scores = util.pytorch_cos_sim(query_embedding, topic_embeddings)
        static_scores = util.pytorch_cos_sim(query_embedding, static_embeddings)
        max_score = max(max_score, topic_scores.max().item(), static_scores.max().item())

    if max_score >= threshold or academic_ratio >= 0.2 or matching_topics:
        return {
            "is_relevant": True,
            "confidence_score": max_score,
            "matched_topics": matching_topics,
        }

    return {
        "is_relevant": False,
        "confidence_score": max_score,
        "reason": "Insufficient topic relevance",
    }


def find_static_answer(query, similarity_threshold=0.7):
    """Find the best matching static answer."""
    query_lower = query.lower().strip()
    processed = preprocess_query(query)
    query_tokens = processed["tokens"]

    for question in static_questions:
        if query_lower == question.lower().strip():
            return {
                "found": True,
                "answer": STATIC_QA[question],
                "score": 1.0,
                "matched_question": question,
            }

    best_question, best_score = best_static_question_score(query, query_tokens)
    if best_question and best_score >= similarity_threshold:
        return {
            "found": True,
            "answer": STATIC_QA[best_question],
            "score": best_score,
            "matched_question": best_question,
        }

    if ensure_semantic_embeddings():
        model, util = get_sentence_model()
        query_embedding = model.encode(query, convert_to_tensor=True)
        cosine_scores = util.pytorch_cos_sim(query_embedding, static_embeddings)
        best_match_idx = cosine_scores.argmax().item()
        best_match_score = cosine_scores[0][best_match_idx].item()

        if best_match_score >= similarity_threshold:
            return {
                "found": True,
                "answer": STATIC_QA[static_questions[best_match_idx]],
                "score": best_match_score,
                "matched_question": static_questions[best_match_idx],
            }
        best_score = max(best_score, best_match_score)

    return {
        "found": False,
        "score": best_score,
    }


def process_query(query):
    """Check relevancy, then static answers, then optional text generation."""
    relevancy_result = check_relevancy(query, threshold=0.5)
    if not relevancy_result["is_relevant"]:
        message = "I can only help with enrollment-related questions. "
        if "non-academic" in relevancy_result.get("reason", ""):
            message += f"Your question appears to contain {relevancy_result['reason']}."
        else:
            message += "Please ask about enrollment, registration, or academics."
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


def format_response(response_text):
    response_text = escape(response_text, quote=False)
    formatted_text = "<div class='chatbot-response'>"
    in_numbered_list = False
    in_bullet_list = False

    def add_www(match):
        url = match.group(1)
        if not url.startswith("www.") and not url.startswith("https://www.") and not url.startswith("http://www."):
            url = re.sub(r"(https?://)", r"\1www.", url)
        return f"<a href='{url}'>{url}</a>"

    urls = {}
    url_pattern = r"(http[s]?://[^\s<]+)"

    def extract_urls(match):
        url_id = f"__URL_{len(urls)}__"
        urls[url_id] = add_www(match)
        return url_id

    response_text = re.sub(url_pattern, extract_urls, response_text)

    def insert_br_outside_url(text):
        pattern = r"(?<!http:)(?<!https:):(?!\d)"
        return re.sub(pattern, r":<br>", text)

    response_text = insert_br_outside_url(response_text)

    for url_id, url_html in urls.items():
        response_text = response_text.replace(url_id, url_html)

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


def deployed_fallback_message():
    return (
        "I can answer common enrollment questions, but the AI response service is not configured yet. "
        "Add OPENROUTER_API_KEY in Vercel environment variables to enable generated answers."
    )


def temporary_service_message(query):
    best_question, best_score = best_static_question_score(query, preprocess_query(query)["tokens"])
    if best_question and best_score >= 0.35:
        return STATIC_QA[best_question]

    return (
        "I can help with enrollment questions, but the live response service is temporarily unavailable. "
        "Please try again in a moment or ask one of the suggested questions below."
    )


def build_context_block(query):
    matches = get_top_static_matches(query, limit=OPENROUTER_MAX_CONTEXT_ITEMS)
    relevant_matches = [match for match in matches if match[0] >= 0.2]

    if not relevant_matches:
        return "No close FAQ matches were found."

    context_lines = []
    for _, question in relevant_matches:
        answer = STATIC_QA.get(question, "")
        context_lines.append(f"Q: {question}\nA: {answer}")

    return "\n\n".join(context_lines)


def stream_openrouter_response(prompt):
    client = get_llm_client()
    if not client:
        yield build_meta_event(source="fallback", reason="missing_openrouter_key")
        yield format_response(deployed_fallback_message())
        yield "[END]"
        return

    system_prompt = (
        "You are NaviBot, a helpful enrollment assistant for SAMCIS students, especially BSIT and BSCS. "
        "Answer only enrollment-related, registration-related, scheduling, tuition, requirements, and academic process questions. "
        "If the user asks about unrelated topics, politely refuse and redirect them to enrollment concerns. "
        "Use the provided FAQ context when it is relevant. "
        "Keep responses concise, clear, and student-friendly. "
        "When listing steps, use numbered or bulleted formatting."
    )
    faq_context = build_context_block(prompt)

    try:
        extra_headers = {}
        if OPENROUTER_SITE_URL:
            extra_headers["HTTP-Referer"] = OPENROUTER_SITE_URL
        if OPENROUTER_APP_NAME:
            extra_headers["X-Title"] = OPENROUTER_APP_NAME

        stream = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            temperature=0.2,
            max_tokens=OPENROUTER_MAX_TOKENS,
            stream=True,
            stream_options={"include_usage": True},
            extra_headers=extra_headers or None,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "system", "content": f"Relevant FAQ context:\n{faq_context}"},
                {"role": "user", "content": prompt},
            ],
        )

        accumulated_response = ""
        sent_source_meta = False
        for chunk in stream:
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                yield build_meta_event(
                    source="openrouter",
                    model=OPENROUTER_MODEL,
                    prompt_tokens=getattr(usage, "prompt_tokens", None),
                    completion_tokens=getattr(usage, "completion_tokens", None),
                    total_tokens=getattr(usage, "total_tokens", None),
                    max_tokens=OPENROUTER_MAX_TOKENS,
                )

            delta = ""
            choices = getattr(chunk, "choices", None) or []
            if choices:
                delta = getattr(choices[0].delta, "content", "") or ""
            if not delta:
                continue

            if not sent_source_meta:
                yield build_meta_event(
                    source="openrouter",
                    model=OPENROUTER_MODEL,
                    max_tokens=OPENROUTER_MAX_TOKENS,
                )
                sent_source_meta = True

            accumulated_response += delta
            yield format_response(accumulated_response)
    except Exception:
        yield build_meta_event(source="fallback", reason="openrouter_error")
        yield format_response(temporary_service_message(prompt))
    yield "[END]"


def generate_response_stream(prompt):
    llm_enabled = bool(get_llm_client())
    if llm_enabled:
        for chunk in stream_openrouter_response(prompt):
            yield chunk
        return

    model, tokenizer = get_generation_model()
    if not model or not tokenizer:
        yield format_response(deployed_fallback_message())
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
        "semantic_models_enabled": ENABLE_SEMANTIC_MODELS,
        "generative_model_enabled": ENABLE_GENERATIVE_MODEL,
        "openrouter_enabled": bool(OPENROUTER_API_KEY),
        "openrouter_model": OPENROUTER_MODEL,
        "openrouter_max_context_items": OPENROUTER_MAX_CONTEXT_ITEMS,
        "openrouter_max_tokens": OPENROUTER_MAX_TOKENS,
        "vercel": IS_VERCEL,
    }


@app.route("/Data/static_qa.json")
def serve_qa_json():
    return send_from_directory(str(DATA_DIR), "static_qa.json")


@app.route("/chat-stream")
def chat_stream():
    user_input = request.args.get("message", "").strip()
    if not user_input:
        return Response("No message provided.", status=400)

    def generate():
        try:
            if contains_multiple_questions(user_input):
                formatted_response = format_response("Please ask one question at a time.")
                yield f"data: {formatted_response}\n\n"
                yield "data: [END]\n\n"
                return

            result = process_query(user_input)
            if user_input.lower() == "thank you":
                thanks = format_response("No worries! Happy to help!")
                yield f"data: {thanks}\n\n"
                yield "data: [END]\n\n"
                return

            if result["status"] == "not_relevant":
                yield build_meta_event(source="relevancy_guard")
                formatted_response = format_response(result["message"])
                yield f"data: {formatted_response}\n\n"
                yield "data: [END]\n\n"
                return

            if result["status"] == "static_answer":
                yield build_meta_event(source="static_qa")
                formatted_response = format_response(result["message"])
                yield f"data: {formatted_response}\n\n"
                yield "data: [END]\n\n"
                return

            for response in generate_response_stream(user_input):
                if response == "[END]":
                    yield "data: [END]\n\n"
                elif response.startswith("event: meta\n"):
                    yield response
                else:
                    yield f"data: {response}\n\n"
        except Exception as exc:
            print(f"Error in generate(): {exc}")
            error_msg = format_response(temporary_service_message(user_input))
            yield f"data: {error_msg}\n\n"
            yield "data: [END]\n\n"

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
