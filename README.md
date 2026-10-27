# Now Serving

An unofficial helper for questions about Philippine government papers. Right
now it covers passports and PSA birth certificates. It only answers from
articles I've written and checked against the DFA and PSA websites, it shows
where each answer came from, and it says so when it doesn't know.

**Try it:** https://danil-tzn31.github.io/Now-Serving/

Not affiliated with the DFA, PSA or any government agency. Always check the
official page before you go.

## Why I made this

Requirements for government documents are spread across different pages,
change from time to time, and are easy to get wrong. People end up asking
around, lining up twice, or paying fixers. I wanted something that gives a
straight answer with the official link next to it, and that refuses to guess.

## What it can help with

- Getting or renewing a passport, including for children
- Lost or damaged passports, and claiming a finished one
- Ordering a PSA birth certificate online or in person, or for someone else
- What to do when PSA has no record of your birth, or when there's a mistake
  on it

You can ask in English, Filipino or Taglish, and it answers in the same
language. Every answer shows its source and the date I last checked it.

## What it won't do

- Answer anything outside those topics. NBI clearance, driver's licenses and
  PhilSys aren't covered yet, so it says it doesn't have an article and points
  you to the agency.
- Help with fixers, bribes or fake documents.
- Book appointments or fill in forms for you.
- Keep your questions. They aren't stored, and phone or ID numbers are hidden
  before the question is processed.

## How it works

1. **Articles.** I wrote 10 short articles from the official DFA and PSA
   pages, each with its sources and the date I checked it.
2. **Search.** Your question is matched against those articles. If nothing is
   close enough, you get the "no article yet" reply and the model is never
   asked.
3. **Safety checks.** Before searching, the question is screened for fixers
   and fake documents, and personal numbers are masked. After the answer is
   written, a second check makes sure it's actually supported by the articles.
4. **Answer.** A small language model writes a short reply using only the
   articles that matched, in the language you asked in.

## How well it works

I test it with 20 questions: 12 it should answer (3 in Taglish, and one with
an ID number pasted in), 5 it doesn't cover, and 3 it should refuse for
safety. Each run is saved in
[evals/reports](evals/reports).

| | v0.1 | v0.2 | v0.3 |
| --- | --- | --- | --- |
| Found the right article | 8/12 | 10/12 | 12/12 |
| Correct answers | 6/12 | 8/12 | 10/12 |
| Refused when it should | 7/8 | 8/8 | 8/8 |
| Answers with made-up fees or days | 0 | 0 | 0 |
| Taglish questions answered in Taglish | 0/3 | 3/3 | 3/3 |

What changed between runs:

- **v0.1 → v0.2:** the safety rules were too broad and blocked 4 real
  questions, like "Can I expedite my passport?". I narrowed them and changed
  the prompt so Taglish questions get Taglish answers.
- **v0.2 → v0.3:** the model's language choice was unreliable, so the code now
  decides it. The model was also refusing questions whose answer is "no", and
  ignoring the question when a number was masked. Both fixed.

The two v0.3 misses are the grader, not the bot. One answer was marked wrong
for saying walk-ins need an appointment, which they do. The other test was
stricter than the article. The grader is another AI model, so I also check
answers by hand. Details for each change are in
[docs/decisions.md](docs/decisions.md).

## Known limits

- Only 10 articles so far, all about passports and PSA birth certificates.
- Fees and rules change. Each answer shows when its article was last checked,
  but an article can be out of date before I catch it.
- Questions that mix topics, or very long ones, can pull in loosely related
  articles as extra sources.
- It's a demo on a small budget, so it limits how many questions it takes at
  once.

## For developers

Built on AWS, using only Amazon's own models.

| Part | What I used |
| --- | --- |
| Articles | Markdown with YAML front matter in [articles/](articles) |
| Search | Amazon Bedrock Knowledge Base, S3 Vectors, Titan Text Embeddings V2 |
| Answers | Amazon Nova Lite through the Bedrock Converse API |
| Safety | Bedrock Guardrails: denied topics, PII masking, grounding check |
| API | AWS Lambda (Python 3.12) and API Gateway, deployed with AWS SAM |
| Page | Plain HTML, CSS and JavaScript on GitHub Pages |
| Evaluation | Python scripts, with Nova Pro grading some checks |

```
articles/      the 10 articles
backend/       Lambda handler and prompt versions
web/           the chat page
evals/         test questions, runner, grader and reports
scripts/       build and sync articles to the Knowledge Base
tests/         unit tests for the Lambda (pytest, botocore Stubber)
docs/          setup notes and a log of decisions
template.yaml  SAM template for the API
```

Run the tests:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
```

Setting up your own copy (Knowledge Base, guardrail, deploy) is written up in
[docs/setup.md](docs/setup.md). Run an eval against a deployed API with:

```bash
export ASK_URL=https://your-api-id.execute-api.us-east-1.amazonaws.com/ask
python evals/run_eval.py v0.4
python evals/grade.py evals/runs/$(date +%F)-v0.4.jsonl
```

## Sources

Articles are written from the
[DFA Office of Consular Affairs](https://consular.dfa.gov.ph/),
the [Philippine Statistics Authority](https://psa.gov.ph/) and
[PSA Helpline](https://psahelpline.ph/). Each article lists the exact pages it
used. For official help, use those sites or the eGovPH app.

## License

MIT
