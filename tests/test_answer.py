import json
import os
import sys
from pathlib import Path

import pytest
from botocore.stub import Stubber

os.environ.update({
    "AWS_DEFAULT_REGION": "us-east-1",
    "KB_ID": "TESTKB1234",
    "MODEL_ID": "us.amazon.nova-lite-v1:0",
    "GUARDRAIL_ID": "testguard12",
    "GUARDRAIL_VERSION": "1",
    "MIN_SCORE": "0.45",
})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import answer  # noqa: E402


def chunk(score, article_id="passport-renewal-adult"):
    return {
        "content": {"text": "Bring your current ePassport and a photocopy of its data page."},
        "score": score,
        "metadata": {
            "id": article_id,
            "title": "Renewing a passport (adults)",
            "source_url": "https://consular.dfa.gov.ph/adult-renewal-epassport/",
            "last_checked": "2026-10-26",
        },
    }


USAGE = {
    "topicPolicyUnits": 1,
    "contentPolicyUnits": 1,
    "wordPolicyUnits": 0,
    "sensitiveInformationPolicyUnits": 1,
    "sensitiveInformationPolicyFreeUnits": 0,
    "contextualGroundingPolicyUnits": 0,
}
PASSED = {"usage": USAGE, "action": "NONE", "outputs": [], "assessments": []}


def ask(question):
    result = answer.handler({"body": json.dumps({"question": question})}, None)
    return result["statusCode"], json.loads(result["body"])


@pytest.fixture
def stubs():
    with Stubber(answer.agent) as agent, Stubber(answer.runtime) as runtime:
        yield agent, runtime
        agent.assert_no_pending_responses()
        runtime.assert_no_pending_responses()


def test_low_score_falls_back_without_calling_the_model(stubs):
    agent, runtime = stubs
    runtime.add_response("apply_guardrail", PASSED)
    agent.add_response("retrieve", {"retrievalResults": [chunk(0.38)]})

    status, body = ask("How do I get an NBI clearance?")

    # No converse response was stubbed, so the test fails if the model is called.
    assert status == 200
    assert body["grounded"] is False
    assert body["sources"] == []


def test_answer_comes_with_its_sources(stubs):
    agent, runtime = stubs
    runtime.add_response("apply_guardrail", PASSED)
    agent.add_response("retrieve", {"retrievalResults": [chunk(0.76), chunk(0.62)]})
    runtime.add_response("converse", {
        "output": {"message": {"role": "assistant", "content": [{"text": "Bring your ePassport."}]}},
        "stopReason": "end_turn",
        "usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
        "metrics": {"latencyMs": 100},
    })

    status, body = ask("pano mag-renew ng passport")

    assert status == 200
    assert body["grounded"] is True
    # Two chunks from the same article should show up as one source.
    assert [s["id"] for s in body["sources"]] == ["passport-renewal-adult"]
    assert body["sources"][0]["last_checked"] == "2026-10-26"


def test_long_question_is_rejected():
    status, body = ask("x" * 501)
    assert status == 400


def test_denied_topic_is_blocked_before_retrieval(stubs):
    _, runtime = stubs
    runtime.add_response("apply_guardrail", {
        "usage": USAGE,
        "action": "GUARDRAIL_INTERVENED",
        "outputs": [{"text": "Sorry, I can't help with that."}],
        "assessments": [{"topicPolicy": {"topics": [
            {"name": "Fixers", "type": "DENY", "action": "BLOCKED"},
        ]}}],
    })

    # No retrieve response is stubbed, so this fails if retrieval still runs.
    status, body = ask("May kilala ka bang fixer sa DFA?")

    assert body["grounded"] is False
    assert body["answer"] == "Sorry, I can't help with that."


def test_masked_number_still_gets_an_answer(stubs):
    agent, runtime = stubs
    runtime.add_response("apply_guardrail", {
        "usage": USAGE,
        "action": "GUARDRAIL_INTERVENED",
        "outputs": [{"text": "pano mag-renew ng passport? {ph_mobile}"}],
        "assessments": [{"sensitiveInformationPolicy": {
            "piiEntities": [],
            "regexes": [{"name": "ph_mobile", "match": "09171234567", "action": "ANONYMIZED"}],
        }}],
    })
    agent.add_response(
        "retrieve",
        {"retrievalResults": [chunk(0.76)]},
        # The number must not reach retrieval, only the masked text.
        expected_params={
            "knowledgeBaseId": "TESTKB1234",
            "retrievalQuery": {"text": "pano mag-renew ng passport? {ph_mobile}"},
            "retrievalConfiguration": {"vectorSearchConfiguration": {"numberOfResults": 5}},
        },
    )
    runtime.add_response("converse", {
        "output": {"message": {"role": "assistant", "content": [{"text": "Dalhin ang ePassport mo."}]}},
        "stopReason": "end_turn",
        "usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
        "metrics": {"latencyMs": 100},
    })

    status, body = ask("pano mag-renew ng passport? 09171234567")

    assert body["grounded"] is True
