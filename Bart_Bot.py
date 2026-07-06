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
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash").strip() or "gemini-2.0-flash"
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


GEMINI_MAX_CONTEXT_ITEMS = get_env_int("GEMINI_MAX_CONTEXT_ITEMS", 3)
GEMINI_MAX_TOKENS = get_env_int("GEMINI_MAX_TOKENS", 300)

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
FAQ_VARIANTS = {
    "Where is the enrollment venue for irregular students?": [
        "where is the enrollment venue",
        "where is the venue for irregular students",
        "where do irregular students enroll",
        "where can irregular students enroll",
        "where is irregular enrollment",
    ],
    "Where do regular students enroll?": [
        "where do regular students enroll",
        "where can regular students enroll",
        "where is regular enrollment",
        "where is the venue for regular students",
        "where should regular students enroll",
    ],
    "What is the enrollment venue for regular and irregular students?": [
        "where do i enroll",
        "where can i enroll",
        "where is enrollment",
        "where is the enrollment venue",
        "where should i enroll",
    ],
    "Can I enroll online or onsite?": [
        "can i enroll online",
        "can i enroll onsite",
        "can i enroll in person",
        "is enrollment online or onsite",
        "is enrollment online or in person",
        "online or onsite enrollment",
    ],
    "Where can I find available subjects?": [
        "where can i check my subjects",
        "where can i find my subjects",
        "where do i see available subjects",
        "where can i see my available subjects",
        "where are available subjects listed",
    ],
    "Where can I find the prerequisite of a subject?": [
        "where do i see prerequisites",
        "where can i find prerequisites",
        "where can i check prerequisite subjects",
        "what are the prerequisites for a subject",
        "where is the prerequisite of a subject found",
    ],
    "What payment methods are available?": [
        "what payment methods are available",
        "how can i pay",
        "what are the payment options",
        "what payment options do i have",
        "can i pay via gcash",
        "can i pay via dragonpay",
        "can i pay by card",
        "payment methods",
    ],
}
FOLLOW_UP_HINTS = (
    "how about",
    "what about",
    "what if",
    "and if",
    "if i'm",
    "if im",
    "if i am",
    "for regular",
    "for irregular",
    "online",
    "onsite",
    "in person",
)
FOLLOW_UP_REFERENCES = {"there", "that", "it", "this", "those", "them"}
TOPIC_PATTERNS = {
    "enrollment_venue": (
        "enroll", "enrollment", "venue", "student portal", "devesse", "devesee",
        "plaza", "regular student", "irregular student",
    ),
    "available_subjects": (
        "available subjects", "available subject", "subjects", "curriculum checklist",
        "checklist", "my subjects",
    ),
    "prerequisite": (
        "prerequisite", "prerequisites", "prereq", "pre requisite", "pre-requisite",
    ),
    "payment": (
        "payment", "pay", "tuition", "dragonpay", "upay", "bdo", "cash", "check",
        "card", "debit", "credit", "bukas", "gcash",
    ),
    "enrollment_mode": (
        "online", "onsite", "in person", "in-person", "face to face", "portal",
    ),
}

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


def infer_topic(text):
    lowered_text = text.lower()
    for topic, patterns in TOPIC_PATTERNS.items():
        if any(pattern in lowered_text for pattern in patterns):
            return topic
    return None


def is_follow_up_query(query):
    lowered_query = query.lower().strip()
    query_tokens = set(tokenize_text(lowered_query))
    return (
        any(hint in lowered_query for hint in FOLLOW_UP_HINTS)
        or bool(query_tokens & FOLLOW_UP_REFERENCES)
        or len(query_tokens) <= 6
    )


def resolve_follow_up_query(query, history):
    if not history:
        return query

    lowered_query = query.lower().strip()
    current_topic = infer_topic(query)
    previous_topic = None
    for entry in reversed(history):
        previous_topic = infer_topic(entry["text"])
        if previous_topic:
            break

    if current_topic == "prerequisite":
        return "Where can I find the prerequisite of a subject?"
    if current_topic == "available_subjects":
        return "Where can I find available subjects?"
    if current_topic == "payment":
        return "What payment methods are available?"
    if current_topic == "enrollment_mode":
        if "regular" in lowered_query:
            return "Where do regular students enroll?"
        if "irregular" in lowered_query:
            return "Where do irregular students enroll?"
        return "Can I enroll online or onsite?"
    if current_topic == "enrollment_venue" and "regular" in lowered_query:
        return "Where do regular students enroll?"
    if current_topic == "enrollment_venue" and "irregular" in lowered_query:
        return "Where do irregular students enroll?"

    if not previous_topic or not is_follow_up_query(query):
        return query

    if previous_topic == "enrollment_venue":
        if "regular" in lowered_query:
            return "Where do regular students enroll?"
        if "irregular" in lowered_query:
            return "Where do irregular students enroll?"
        if any(keyword in lowered_query for keyword in ("online", "onsite", "in person", "portal")):
            return "Can I enroll online or onsite?"
        return "What is the enrollment venue for regular and irregular students?"

    if previous_topic == "available_subjects":
        if any(keyword in lowered_query for keyword in ("prerequisite", "prerequisites", "prereq")):
            return "Where can I find the prerequisite of a subject?"
        return "Where can I find available subjects?"

    if previous_topic == "prerequisite":
        return "Where can I find the prerequisite of a subject?"

    if previous_topic == "payment":
        return "What payment methods are available?"

    if previous_topic == "enrollment_mode":
        if "regular" in lowered_query:
            return "Where do regular students enroll?"
        if "irregular" in lowered_query:
            return "Where do irregular students enroll?"
        return "Can I enroll online or onsite?"

    return query


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
    if not GEMINI_API_KEY:
        return None

    try:
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        llm_client = genai
    except Exception as exc:
        print(f"Unable to initialize Gemini client: {exc}")
        llm_client = None

    return llm_client


def question_similarity_score(query, query_tokens, question):
    candidates = [question.lower().strip()]
    candidates.extend(variant.lower().strip() for variant in FAQ_VARIANTS.get(question, []))

    best_score = 0.0
    normalized_query = query.lower().strip()
    for candidate in candidates:
        candidate_tokens = set(tokenize_text(candidate)) - STOP_WORDS
        overlap_score = len(query_tokens & candidate_tokens) / max(len(candidate_tokens), 1)
        sequence_score = SequenceMatcher(None, normalized_query, candidate).ratio()
        substring_score = 1.0 if normalized_query in candidate or candidate in normalized_query else 0.0
        best_score = max(best_score, overlap_score, sequence_score, substring_score)
    return best_score


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
        exact_candidates = [question.lower().strip()]
        exact_candidates.extend(variant.lower().strip() for variant in FAQ_VARIANTS.get(question, []))
        if query_lower in exact_candidates:
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
        "Add GEMINI_API_KEY in Vercel environment variables to enable generated answers."
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
    matches = get_top_static_matches(query, limit=GEMINI_MAX_CONTEXT_ITEMS)
    relevant_matches = [match for match in matches if match[0] >= 0.2]

    if not relevant_matches:
        return "No close FAQ matches were found."

    context_lines = []
    for _, question in relevant_matches:
        answer = STATIC_QA.get(question, "")
        context_lines.append(f"Q: {question}\nA: {answer}")

    return "\n\n".join(context_lines)


def extract_gemini_chunk_text(chunk):
    text = getattr(chunk, "text", None)
    if text:
        return text

    candidates = getattr(chunk, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        text_parts = [getattr(part, "text", "") for part in parts if getattr(part, "text", "")]
        if text_parts:
            return "".join(text_parts)
    return ""


def stream_gemini_response(prompt):
    genai = get_llm_client()
    if not genai:
        yield build_meta_event(
            source="fallback",
            reason="missing_gemini_key",
            gemini_key_present=bool(GEMINI_API_KEY),
            gemini_model=GEMINI_MODEL,
        )
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
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction=system_prompt,
            generation_config={
                "temperature": 0.2,
                "max_output_tokens": GEMINI_MAX_TOKENS,
            },
        )
        full_prompt = (
            f"Relevant FAQ context:\n{faq_context}\n\n"
            f"Student question:\n{prompt}"
        )
        stream = model.generate_content(full_prompt, stream=True)

        accumulated_response = ""
        sent_source_meta = False
        for chunk in stream:
            delta = extract_gemini_chunk_text(chunk)
            if not delta:
                continue

            if not sent_source_meta:
                yield build_meta_event(
                    source="gemini",
                    model=GEMINI_MODEL,
                    max_tokens=GEMINI_MAX_TOKENS,
                )
                sent_source_meta = True

            accumulated_response += delta
            yield format_response(accumulated_response)
    except Exception as exc:
        yield build_meta_event(
            source="fallback",
            reason="gemini_error",
            gemini_model=GEMINI_MODEL,
            error=str(exc)[:300],
        )
        yield format_response(temporary_service_message(prompt))
    yield "[END]"


def generate_response_stream(prompt):
    llm_enabled = bool(get_llm_client())
    if llm_enabled:
        for chunk in stream_gemini_response(prompt):
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
        "gemini_enabled": bool(GEMINI_API_KEY),
        "gemini_key_present": bool(GEMINI_API_KEY),
        "gemini_model": GEMINI_MODEL,
        "gemini_max_context_items": GEMINI_MAX_CONTEXT_ITEMS,
        "gemini_max_tokens": GEMINI_MAX_TOKENS,
        "vercel": IS_VERCEL,
    }


@app.route("/Data/static_qa.json")
def serve_qa_json():
    return send_from_directory(str(DATA_DIR), "static_qa.json")


@app.route("/chat-stream")
def chat_stream():
    user_input = request.args.get("message", "").strip()
    history = parse_history_param(request.args.get("history", ""))
    if not user_input:
        return Response("No message provided.", status=400)

    def generate():
        try:
            if contains_multiple_questions(user_input):
                formatted_response = format_response("Please ask one question at a time.")
                yield f"data: {formatted_response}\n\n"
                yield "data: [END]\n\n"
                return

            resolved_input = resolve_follow_up_query(user_input, history)
            result = process_query(resolved_input)
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

            for response in generate_response_stream(resolved_input):
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
