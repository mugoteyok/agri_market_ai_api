"""AI customer-support answer service for Agri AI Assist.

This module uses Gemini REST APIs and the existing Supabase FAQ RPC.
It does not create tickets or perform account/payment actions.
"""

import os
import re
from typing import Any

import requests
from dotenv import load_dotenv

from database import get_admin_supabase


load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_EMBEDDING_MODEL = os.getenv(
    "GEMINI_EMBEDDING_MODEL",
    "gemini-embedding-2",
)
GEMINI_SUPPORT_MODEL = os.getenv(
    "GEMINI_SUPPORT_MODEL",
    "gemini-3.8-flash",
)
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
EMBEDDING_DIMENSIONS = 768
FAQ_SEARCH_THRESHOLD = float(
    os.getenv("SUPPORT_FAQ_SEARCH_THRESHOLD", "0.50")
)
FAQ_CONFIDENCE_THRESHOLD = float(
    os.getenv("SUPPORT_FAQ_CONFIDENCE_THRESHOLD", "0.66")
)


class SupportAIConfigurationError(Exception):
    """Raised when required AI configuration is missing."""


class SupportAIProviderError(Exception):
    """Raised when a Gemini API request fails or returns invalid data."""


def _api_headers() -> dict[str, str]:
    key = os.getenv("GEMINI_API_KEY") or GEMINI_API_KEY
    if not key:
        raise SupportAIConfigurationError(
            "GEMINI_API_KEY is not configured on the backend."
        )
    return {
        "Content-Type": "application/json",
        "x-goog-api-key": key,
    }


def _post_gemini(url: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        response = requests.post(
            url,
            headers=_api_headers(),
            json=body,
            timeout=(5, 30),
        )
    except requests.RequestException as exc:
        raise SupportAIProviderError("Gemini service is unreachable.") from exc

    if not response.ok:
        # Do not log or return the provider body; it may include user prompt data.
        print("SUPPORT GEMINI REQUEST FAILED. HTTP STATUS:", response.status_code)
        raise SupportAIProviderError(
            f"Gemini request failed with HTTP {response.status_code}."
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise SupportAIProviderError("Gemini returned an invalid response.") from exc

    if not isinstance(payload, dict):
        raise SupportAIProviderError("Gemini returned an unexpected response.")
    return payload


def generate_embedding(text: str, *, document_title: str | None = None) -> list[float]:
    """Generate a 768-dimensional Gemini Embedding 2 vector."""

    if document_title is None:
        formatted_text = f"task: question answering | query: {text.strip()}"
    else:
        title = document_title.strip() or "none"
        formatted_text = f"title: {title} | text: {text.strip()}"

    url = (
        f"{GEMINI_API_BASE}/models/"
        f"{GEMINI_EMBEDDING_MODEL}:embedContent"
    )
    payload = _post_gemini(
        url,
        {
            "content": {"parts": [{"text": formatted_text}]},
            "output_dimensionality": EMBEDDING_DIMENSIONS,
        },
    )

    embedding = payload.get("embedding", {}).get("values")
    if not isinstance(embedding, list) or len(embedding) != EMBEDDING_DIMENSIONS:
        raise SupportAIProviderError(
            "Gemini returned an embedding with an unexpected dimension."
        )

    try:
        return [float(value) for value in embedding]
    except (TypeError, ValueError) as exc:
        raise SupportAIProviderError("Gemini returned an invalid embedding.") from exc


def _is_handoff_request(question: str) -> bool:
    patterns = (
        r"\b(speak|talk|connect|transfer)\b.{0,35}\b(human|agent|person|support|staff|representative)\b",
        r"\b(human|agent|person|representative)\b.{0,35}\b(help|please|support)\b",
        r"\b(call support|contact support|speak to someone|talk to someone)\b",
    )
    return any(re.search(pattern, question, re.IGNORECASE) for pattern in patterns)


def _is_agriculture_question(question: str) -> bool:
    return bool(
        re.search(
            r"\b(crop disease|plant disease|pest|fungicide|fertili[sz]er|soil test|leaf rust|crop diagnosis|maize disease|cassava disease|banana disease)\b",
            question,
            re.IGNORECASE,
        )
    )


def _log_unanswered(
    question: str,
    locale: str,
    channel: str,
    reason: str,
    best_match_score: float | None = None,
    faq_id: str | None = None,
) -> None:
    """Store only the question and retrieval metadata, not user identity/history."""

    try:
        get_admin_supabase().from_("support_unanswered").insert(
            {
                "question": question[:2000],
                "locale": locale,
                "channel": channel,
                "reason": reason,
                "best_match_score": best_match_score,
                "faq_id": faq_id,
            }
        ).execute()
    except Exception as exc:
        # Do not fail customer support because optional analytics logging failed.
        print("SUPPORT UNANSWERED LOGGING FAILED:", type(exc).__name__)


def _search_faqs(embedding: list[float]) -> list[dict[str, Any]]:
    """Search private FAQ data using backend-only service-role access."""
    response = get_admin_supabase().rpc(
        "match_support_faqs",
        {
            "query_embedding": embedding,
            "match_threshold": FAQ_SEARCH_THRESHOLD,
            "match_count": 5,
            "filter_locale": None,
        },
    ).execute()
    return response.data or []


def _generate_grounded_answer(
    question: str,
    locale: str,
    conversation: list[dict[str, str]],
    faq_matches: list[dict[str, Any]],
) -> str:
    locale_name = "Luganda" if locale == "lg" else "English"

    faq_context = []
    for index, faq in enumerate(faq_matches[:4], start=1):
        faq_context.append(
            f"FAQ {index}\nQuestion: {faq.get('question', '')}\n"
            f"Approved answer: {faq.get('answer', '')}"
        )

    recent_context = []
    for item in conversation[-8:]:
        role = item.get("role", "user")
        content = str(item.get("content", "")).strip()[:1200]
        if content:
            label = "Customer" if role == "user" else "Assistant"
            recent_context.append(f"{label}: {content}")

    system_instruction = (
        "You are the Agri AI Assist in-app customer-support assistant. "
        "Answer only questions about using the Agri AI Assist app and its "
        "support, account, marketplace, orders, wallet, subscriptions, and "
        "related app workflows. Use only the approved FAQ context supplied "
        "in the user input. Never invent app features, prices, policies, "
        "account actions, payment status, or troubleshooting steps. Do not "
        "claim that you created a ticket, changed an account, contacted a "
        "person, or completed an action. Do not request passwords, PINs, "
        "one-time codes, or payment credentials. If the supplied FAQs do not "
        "support a complete answer, say you cannot verify the answer and ask "
        "whether the customer wants to create a support request. Agricultural "
        "diagnosis, crop treatment, and agronomy questions belong in the app's "
        "Ask AI feature; direct the customer there. Reply in "
        f"{locale_name}. Use short, natural sentences suitable for being read "
        "aloud. Do not use markdown tables or long lists."
    )

    prompt = (
        "Approved support FAQ context:\n"
        + "\n\n".join(faq_context)
        + "\n\nRecent conversation (context only):\n"
        + ("\n".join(recent_context) if recent_context else "None")
        + "\n\nLatest customer question:\n"
        + question
        + "\n\nAnswer the latest question using only the approved FAQ context."
    )

    payload = _post_gemini(
        f"{GEMINI_API_BASE}/interactions",
        {
            "model": GEMINI_SUPPORT_MODEL,
            "store": False,
            "system_instruction": system_instruction,
            "input": prompt,
        },
    )

    output_parts: list[str] = []
    for step in payload.get("steps", []) or []:
        if not isinstance(step, dict) or step.get("type") != "model_output":
            continue
        for item in step.get("content", []) or []:
            if isinstance(item, dict) and item.get("type") == "text":
                value = item.get("text")
                if isinstance(value, str) and value.strip():
                    output_parts.append(value.strip())

    if not output_parts and isinstance(payload.get("output_text"), str):
        output_parts.append(payload["output_text"].strip())

    answer = "\n".join(part for part in output_parts if part).strip()
    if not answer:
        raise SupportAIProviderError("Gemini did not return a text answer.")

    return answer[:2500]


def _offer_ticket(reply: str, *, action: str = "offer_ticket") -> dict[str, Any]:
    return {
        "success": True,
        "reply": reply,
        "action": action,
        "confirmation_required": action == "offer_ticket",
        "source": "fallback",
    }


def answer_support_question(
    question: str,
    conversation: list[dict[str, str]] | None = None,
    locale: str = "en",
    channel: str = "voice",
) -> dict[str, Any]:
    """Retrieve approved FAQs, answer safely, or offer human support."""

    question = question.strip()
    locale = locale.lower().strip()
    conversation = conversation or []

    if not question:
        raise ValueError("Support question cannot be empty.")

    if locale not in {"en", "lg"}:
        locale = "en"

    if _is_handoff_request(question):
        return {
            "success": True,
            "reply": (
                "I can direct you to the human support options. "
                "Please use Call Support to contact the support team."
                if locale == "en"
                else "Nsobola okukulaga engeri yâ€™okutuukirira abakozi ba support. "
                     "Kozesa Call Support okwogera nabo."
            ),
            "action": "handoff",
            "confirmation_required": False,
            "source": "system",
        }

    if _is_agriculture_question(question):
        return {
            "success": True,
            "reply": (
                "That question is better handled by Ask AI, which is designed "
                "for crop diagnosis and agricultural guidance. Please open Ask AI in the app."
                if locale == "en"
                else "Ekibuuzo kino kirungi okukibuuza mu Ask AI, eyakolebwa ku "
                     "kukebera endwadde zâ€™ebirime nâ€™okufuna amagezi agâ€™obulimi. "
                     "Bikkula Ask AI mu pulogulaamu."
            ),
            "action": "open_ask_ai",
            "confirmation_required": False,
            "source": "system",
        }

    if not (os.getenv("GEMINI_API_KEY") or GEMINI_API_KEY):
        return _offer_ticket(
            "The AI support assistant is not configured yet. You can still "
            "submit a support request or use Call Support."
        )

    try:
        query_embedding = generate_embedding(question)
        matches = _search_faqs(query_embedding)
    except SupportAIConfigurationError:
        return _offer_ticket(
            "The AI support assistant is not configured yet. Please use "
            "Call Support or submit a support request."
        )
    except Exception as exc:
        print("SUPPORT FAQ RETRIEVAL FAILED:", type(exc).__name__)
        _log_unanswered(question, locale, channel, "generation_failed")
        return _offer_ticket(
            "I'm having trouble checking the support information right now. "
            "Would you like to submit a support request?"
        )

    if not matches:
        _log_unanswered(question, locale, channel, "no_match")
        return _offer_ticket(
            "I don't have a verified answer for that yet. Would you like "
            "me to help you create a support request?"
        )

    best = matches[0]
    best_score = float(best.get("similarity") or 0.0)
    best_faq_id = str(best.get("faq_id") or "") or None

    if best_score < FAQ_CONFIDENCE_THRESHOLD:
        _log_unanswered(
            question,
            locale,
            channel,
            "below_threshold",
            best_score,
            best_faq_id,
        )
        return _offer_ticket(
            "I found some information, but I'm not confident it answers "
            "your question. Would you like to submit a support request?"
        )

    try:
        reply = _generate_grounded_answer(
            question,
            locale,
            conversation,
            matches,
        )
    except Exception as exc:
        print("SUPPORT ANSWER GENERATION FAILED:", type(exc).__name__)
        _log_unanswered(
            question,
            locale,
            channel,
            "generation_failed",
            best_score,
            best_faq_id,
        )
        return _offer_ticket(
            "I found relevant support information but couldn't prepare an "
            "answer right now. Would you like to submit a support request?"
        )

    return {
        "success": True,
        "reply": reply,
        "action": "answer",
        "confirmation_required": False,
        "source": "faq",
        "faq_id": best_faq_id,
        "confidence": round(best_score, 4),
    }
