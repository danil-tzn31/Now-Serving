"""Grade a saved eval run and write a markdown report.

Usage: python evals/grade.py evals/runs/2026-10-28-v0.1.jsonl
Most checks are plain code. Nova Pro only judges correctness and language,
and those verdicts get spot-checked by hand (see the report).
"""

import json
import re
import sys
from pathlib import Path

import boto3
import yaml

HERE = Path(__file__).resolve().parent
ARTICLES = HERE.parent / "articles"
GRADER = "us.amazon.nova-pro-v1:0"

bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

# Pesos and day counts are what hurt most if the bot gets them wrong.
NUMBER = re.compile(r"₱\s?[\d,]+|\b\d+\s+(?:business |working )?days?\b", re.IGNORECASE)


def article_text(article_id):
    for path in ARTICLES.glob(f"*/{article_id}.md"):
        return path.read_text(encoding="utf-8")
    return ""


def invented_numbers(reply):
    """Numbers in the answer that don't appear in any article it cited."""
    sources = " ".join(article_text(s["id"]) for s in reply.get("sources", []))
    squash = lambda text: re.sub(r"[\s,]", "", text.lower())
    return [n for n in NUMBER.findall(reply.get("answer", "")) if squash(n) not in squash(sources)]


def judge(prompt):
    response = bedrock.converse(
        modelId=GRADER,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 200, "temperature": 0},
    )
    text = response["output"]["message"]["content"][0]["text"]
    match = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        return json.loads(match.group(0))
    except (AttributeError, json.JSONDecodeError):
        return {"pass": False, "reason": f"grader reply not readable: {text[:80]}"}


def judge_correctness(q, answer):
    must = "\n".join(f"- {m}" for m in q.get("must_include", [])) or "- (none)"
    must_not = "\n".join(f"- {m}" for m in q.get("must_not_include", [])) or "- (none)"
    return judge(f"""You are checking a support bot's answer against a list of facts.

Question: {q['question']}

Answer:
{answer}

The answer must cover each of these (same meaning is enough, wording can differ):
{must}

The answer must not say any of these:
{must_not}

Reply with JSON only: {{"pass": true or false, "reason": "one short sentence"}}""")


def judge_language(q, answer):
    return judge(f"""Is this answer written mostly in Filipino or Taglish (not plain English)?

Answer:
{answer}

Reply with JSON only: {{"pass": true or false, "reason": "one short sentence"}}""")


def grade(q, reply):
    if "error" in reply:
        return {"id": q["id"], "type": q["type"], "error": reply["error"]}

    ids = [s["id"] for s in reply.get("sources", [])]
    row = {"id": q["id"], "type": q["type"], "seconds": reply.get("seconds")}

    if q["expect"] == "refuse":
        row["behaved"] = reply.get("grounded") is False
        return row

    row["behaved"] = reply.get("grounded") is True
    row["hit"] = q.get("expected_article") in ids if q.get("expected_article") else None
    row["invented"] = invented_numbers(reply)
    verdict = judge_correctness(q, reply.get("answer", ""))
    row["correct"], row["reason"] = bool(verdict.get("pass")), verdict.get("reason", "")
    if q["language"] == "tl":
        row["language_ok"] = bool(judge_language(q, reply.get("answer", "")).get("pass"))
    return row


def count(rows, key):
    scored = [r for r in rows if r.get(key) is not None]
    return f"{sum(1 for r in scored if r[key])}/{len(scored)}"


def report(run_path, rows):
    answerable = [r for r in rows if "correct" in r]
    refusals = [r for r in rows if "correct" not in r and "error" not in r]
    invented = [r for r in answerable if r["invented"]]
    lines = [
        f"# Eval run: {run_path.stem}",
        "",
        "Prompt: answer_v1 · Chunking: fixed 300/15% · MIN_SCORE: 0.45 · Model: Nova Lite · Grader: Nova Pro",
        "",
        "| Score | Result |",
        "| --- | --- |",
        f"| Retrieval hit rate | {count(answerable, 'hit')} |",
        f"| Correct answers | {count(answerable, 'correct')} |",
        f"| Correct refusals | {count(refusals, 'behaved')} |",
        f"| Answers with invented numbers | {len(invented)} |",
        f"| Taglish answered in Taglish | {count(answerable, 'language_ok')} |",
        f"| Errors | {sum(1 for r in rows if 'error' in r)} |",
        "",
        "Grader agreement with my own check: _/10",
        "",
        "## Failures",
        "",
        "| id | type | what went wrong |",
        "| --- | --- | --- |",
    ]
    for r in rows:
        problems = []
        if "error" in r:
            problems.append(f"error: {r['error']}")
        if r.get("behaved") is False:
            problems.append("should have refused" if "correct" not in r else "refused or blocked a real question")
        if r.get("hit") is False:
            problems.append("expected article not in sources")
        if r.get("correct") is False:
            problems.append(f"grader: {r['reason']}")
        if r.get("invented"):
            problems.append(f"numbers not in sources: {', '.join(r['invented'])}")
        if r.get("language_ok") is False:
            problems.append("answered in English")
        if problems:
            lines.append(f"| {r['id']} | {r['type']} | {'; '.join(problems)} |")
    lines += ["", "## What I'll change next", "", "_one line_", ""]
    return "\n".join(lines)


def main():
    run_path = Path(sys.argv[1])
    questions = {q["id"]: q for q in yaml.safe_load((HERE / "questions.yaml").read_text())}
    replies = [json.loads(line) for line in run_path.read_text().splitlines() if line.strip()]

    rows = []
    for reply in replies:
        rows.append(grade(questions[reply["id"]], reply))
        print(reply["id"], "graded")

    out = HERE / "reports" / f"{run_path.stem}.md"
    out.write_text(report(run_path, rows), encoding="utf-8")
    print(f"wrote {out.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
