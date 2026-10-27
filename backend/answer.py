"""Lambda handler for POST /ask."""

import json
import os
import re
from pathlib import Path

import boto3

KB_ID = os.environ["KB_ID"]
MODEL_ID = os.environ["MODEL_ID"]
GUARDRAIL_ID = os.environ["GUARDRAIL_ID"]
GUARDRAIL_VERSION = os.environ["GUARDRAIL_VERSION"]

# Picked from the first retrieval test: the weakest real question scored 0.49,
# a question with no article at all scored 0.38. See docs/setup.md.
MIN_SCORE = float(os.environ.get("MIN_SCORE", "0.45"))
MAX_QUESTION_LENGTH = 500

# Nova Lite kept picking the wrong language when left to decide (English
# questions got Taglish replies after Taglish aliases showed up in the
# articles), so the code decides and tells it. Common Filipino words only;
# one is enough to count as Taglish. "may" is left out because it's also
# English ("May I renew online?").
FILIPINO_WORDS = {
    "ako", "ang", "ano", "ba", "bakit", "dito", "ito", "kailan", "kapag",
    "ko", "kong", "kung", "mag", "magkano", "mga", "mo", "na", "nag",
    "nawala", "ng", "ni", "pa", "paano", "pag", "pano", "po", "pwede",
    "saan", "sa", "wala", "yung",
}

PROMPT_VERSION = "v3"
PROMPT = (Path(__file__).parent / "prompts" / f"answer_{PROMPT_VERSION}.txt").read_text()

FALLBACK = (
    "I don't have a checked article for that yet. For passports, call the DFA "
    "at (02) 8651-9400. For PSA documents, go to psa.gov.ph."
)
# Only used if the guardrail ever returns a block without its own message.
# The real wording lives in the guardrail settings in the console.
BLOCKED = "Sorry, I can't help with that. For official help, contact the agency directly."

agent = boto3.client("bedrock-agent-runtime")
runtime = boto3.client("bedrock-runtime")


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return reply(400, {"error": "Send JSON like {\"question\": \"...\"}"})

    question = str(body.get("question", "")).strip()
    if not question:
        return reply(400, {"error": "Ask a question first."})
    if len(question) > MAX_QUESTION_LENGTH:
        return reply(400, {"error": f"Keep questions under {MAX_QUESTION_LENGTH} characters."})

    # Check the question on its own first. Otherwise a fixer question that
    # doesn't match any article just gets the "no article" reply, and the
    # denied topics never get a say.
    original = question
    question, blocked_message, blocked_by = check_question(question)
    if blocked_message:
        log(grounded=False, reason="guardrail_input", blocked_by=blocked_by)
        return reply(200, answer_body(blocked_message, [], grounded=False))

    chunks = [c for c in retrieve(question) if c["score"] >= MIN_SCORE]

    # Nothing close enough means no answer. The model never gets an empty
    # context, because that's exactly when it starts making things up.
    if not chunks:
        log(grounded=False, reason="low_score")
        return reply(200, answer_body(FALLBACK, [], grounded=False))

    articles = format_articles(chunks)
    masked = question != original
    text = ask_model(question, articles, reply_language(question), masked)

    # Prompt v2 asks the model to say NO_ANSWER when the articles don't cover
    # the question. This has to come before the grounding check: "NO_ANSWER"
    # isn't grounded in anything, so the check would block it with a score of
    # zero, and the user got "can't help with that" instead of the fallback.
    if text.strip().startswith("NO_ANSWER"):
        log(grounded=False, reason="model_no_answer")
        return reply(200, answer_body(FALLBACK, [], grounded=False))

    blocked_message, checks = check_answer(question, articles, text)
    if blocked_message:
        log(grounded=False, reason="guardrail_output", checks=checks)
        return reply(200, answer_body(blocked_message, [], grounded=False))

    sources = list_sources(chunks)
    log(grounded=True, articles=[s["id"] for s in sources], top_score=chunks[0]["score"])
    return reply(200, answer_body(text, sources, grounded=True))


def check_question(question):
    result = runtime.apply_guardrail(
        guardrailIdentifier=GUARDRAIL_ID,
        guardrailVersion=GUARDRAIL_VERSION,
        source="INPUT",
        content=[{"text": {"text": question}}],
    )
    if result["action"] != "GUARDRAIL_INTERVENED":
        return question, None, []

    # Masking a phone or ID number also counts as an intervention, so look at
    # what actually happened. Only a block stops the request. The names of
    # whatever blocked it get logged, so false blocks can be traced to a topic.
    blocked_by = []
    for assessment in result.get("assessments", []):
        for policy in assessment.values():
            if not isinstance(policy, dict):
                continue
            for items in policy.values():
                if not isinstance(items, list):
                    continue
                for item in items:
                    if isinstance(item, dict) and item.get("action") == "BLOCKED":
                        blocked_by.append(item.get("name") or item.get("type") or "unknown")

    if blocked_by:
        outputs = result.get("outputs") or [{"text": BLOCKED}]
        return question, outputs[0]["text"], blocked_by

    # Not blocked, so it was masked. Carry on with the masked text.
    masked = result.get("outputs") or [{"text": question}]
    return masked[0]["text"], None, []


def retrieve(question):
    result = agent.retrieve(
        knowledgeBaseId=KB_ID,
        retrievalQuery={"text": question},
        retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 5}},
    )
    return [
        {
            "text": r["content"]["text"],
            "score": r.get("score", 0),
            "meta": r.get("metadata", {}),
        }
        for r in result["retrievalResults"]
    ]


def format_articles(chunks):
    return "\n\n---\n\n".join(
        f"{c['meta'].get('title', 'Article')} (checked {c['meta'].get('last_checked', 'unknown')})\n{c['text']}"
        for c in chunks
    )


def reply_language(question):
    words = set(re.findall(r"[a-z]+", question.lower()))
    return "Taglish" if words & FILIPINO_WORDS else "English"


def system_prompt(language, masked):
    blocks = [{"text": PROMPT}, {"text": f"Reply in {language}."}]
    # With a number masked, the model kept answering the masked bit ("I can't
    # help with ID numbers") instead of the actual question. See q05.
    if masked:
        blocks.append({"text": (
            "Personal numbers in the question were hidden for privacy and show "
            "up in curly braces. Ignore them and answer the rest of the question."
        )})
    return blocks


def ask_model(question, articles, language, masked=False):
    # No guardrail on this call. The question was already checked, and the
    # answer is checked separately below, after the NO_ANSWER test.
    response = runtime.converse(
        modelId=MODEL_ID,
        # The language line goes in the system prompt. In the user message the
        # model sometimes copied it into the answer ("... Reply in Taglish.").
        system=system_prompt(language, masked),
        messages=[{
            "role": "user",
            "content": [{"text": f"Articles:\n\n{articles}\n\nQuestion: {question}"}],
        }],
        inferenceConfig={"maxTokens": 600, "temperature": 0.2},
    )
    text = response["output"]["message"]["content"][0]["text"]
    # Nova Lite still echoes the language line now and then, even from the
    # system prompt. Cheaper to strip it than to keep rewording the prompt.
    return re.sub(r"\s*Reply in (English|Taglish)\.\s*", "\n", text).strip()


def check_answer(question, articles, text):
    # The qualifiers tell the guardrail which part is the source and which is
    # the question. Without them the grounding check has nothing to compare.
    result = runtime.apply_guardrail(
        guardrailIdentifier=GUARDRAIL_ID,
        guardrailVersion=GUARDRAIL_VERSION,
        source="OUTPUT",
        content=[
            {"text": {"text": articles, "qualifiers": ["grounding_source"]}},
            {"text": {"text": question, "qualifiers": ["query"]}},
            {"text": {"text": text, "qualifiers": ["guard_content"]}},
        ],
    )
    if result["action"] != "GUARDRAIL_INTERVENED":
        return None, []

    # Grounding and relevance scores, logged for tuning. No answer text.
    checks = []
    for assessment in result.get("assessments", []):
        for f in assessment.get("contextualGroundingPolicy", {}).get("filters", []):
            if f.get("action") == "BLOCKED":
                checks.append(f"{f['type']} {f['score']:.2f} (needs {f['threshold']})")
        for t in assessment.get("topicPolicy", {}).get("topics", []):
            if t.get("action") == "BLOCKED":
                checks.append(f"topic {t['name']}")

    # Detect-only findings (like a phone number in the answer) also count as
    # an intervention, so only stop if something was actually blocked.
    if not checks:
        return None, []
    outputs = result.get("outputs") or [{"text": BLOCKED}]
    return outputs[0]["text"], checks


def list_sources(chunks):
    seen, sources = set(), []
    for c in chunks:
        meta = c["meta"]
        article_id = meta.get("id")
        if not article_id or article_id in seen:
            continue
        seen.add(article_id)
        sources.append({
            "id": article_id,
            "title": meta.get("title"),
            "url": meta.get("source_url"),
            "last_checked": meta.get("last_checked"),
        })
    return sources


def answer_body(text, sources, grounded):
    return {
        "answer": text,
        "sources": sources,
        "grounded": grounded,
        "prompt_version": PROMPT_VERSION,
    }


def log(**fields):
    # Questions are never logged. People paste ID and phone numbers into these.
    print(json.dumps(fields))


def reply(status, body):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }
