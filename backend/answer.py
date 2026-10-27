"""Lambda handler for POST /ask."""

import json
import os
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

PROMPT_VERSION = "v1"
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
    question, blocked_message = check_question(question)
    if blocked_message:
        log(grounded=False, reason="guardrail_input")
        return reply(200, answer_body(blocked_message, [], grounded=False))

    chunks = [c for c in retrieve(question) if c["score"] >= MIN_SCORE]

    # Nothing close enough means no answer. The model never gets an empty
    # context, because that's exactly when it starts making things up.
    if not chunks:
        log(grounded=False, reason="low_score")
        return reply(200, answer_body(FALLBACK, [], grounded=False))

    text, intervened = ask_model(question, chunks)
    if intervened:
        log(grounded=False, reason="guardrail")
        return reply(200, answer_body(text or BLOCKED, [], grounded=False))

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
        return question, None

    # Masking a phone or ID number also counts as an intervention, so look at
    # what actually happened. Only a block stops the request.
    for assessment in result.get("assessments", []):
        for policy in assessment.values():
            if not isinstance(policy, dict):
                continue
            for items in policy.values():
                if isinstance(items, list) and any(
                    isinstance(i, dict) and i.get("action") == "BLOCKED" for i in items
                ):
                    outputs = result.get("outputs") or [{"text": BLOCKED}]
                    return question, outputs[0]["text"]

    # Not blocked, so it was masked. Carry on with the masked text.
    masked = result.get("outputs") or [{"text": question}]
    return masked[0]["text"], None


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


def ask_model(question, chunks):
    articles = "\n\n---\n\n".join(
        f"{c['meta'].get('title', 'Article')} (checked {c['meta'].get('last_checked', 'unknown')})\n{c['text']}"
        for c in chunks
    )

    # The qualifiers tell the guardrail which part is the source and which is
    # the question. Without them the grounding check has nothing to compare.
    response = runtime.converse(
        modelId=MODEL_ID,
        system=[{"text": PROMPT}],
        messages=[{
            "role": "user",
            "content": [
                {"text": "Articles, then the question:"},
                {"guardContent": {"text": {"text": articles, "qualifiers": ["grounding_source"]}}},
                {"guardContent": {"text": {"text": question, "qualifiers": ["query"]}}},
            ],
        }],
        inferenceConfig={"maxTokens": 600, "temperature": 0.2},
        guardrailConfig={
            "guardrailIdentifier": GUARDRAIL_ID,
            "guardrailVersion": GUARDRAIL_VERSION,
        },
    )
    if response["stopReason"] == "guardrail_intervened":
        # The blocked message from the guardrail settings comes back as the reply.
        content = response["output"]["message"]["content"]
        return (content[0]["text"] if content else None), True
    return response["output"]["message"]["content"][0]["text"], False


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
