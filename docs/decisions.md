# Decisions

## 2026-10-26: Region
Using us-east-1. Singapore has Nova Lite but not Titan Text Embeddings V2,
and the Knowledge Base needs the embedding model in the same region.

## 2026-10-26: Vector store
S3 Vectors instead of OpenSearch Serverless. OpenSearch has a minimum
of about $350/month, which is more than my whole credit balance.

## 2026-10-26: Models
Nova Lite for answers, Nova Pro for grading the eval, Titan V2 for
embeddings. Sticking to Amazon's own models since the account runs on
free credits only.

## 2026-10-27: Guardrail checks the question first
The fixer question scored too low to reach the model, so it got the
"no article" reply instead of being blocked. Now the question goes through
the guardrail before retrieval. Blocked topics stop there; masked numbers
carry on, and only the masked text is searched and sent to the model.

## 2026-10-27: Removed the Legal disputes topic. 
It blocked normal questions about birth records and corrections. Out-of-scope questions are already handled by MIN_SCORE and the model’s NO_ANSWER reply, so the guardrail only keeps topics that are actually harmful (fixers, fake documents).

## 2026-10-27: Fixes from the first evals
The v0.1 eval blocked 4 of 12 real questions. "Expedite" hit the Fixers
topic and a Taglish price question hit Fake documents, so both topics now
only describe the bad act (bribes, forging). Polite refusals still counted
as grounded, so the model now replies NO_ANSWER and the Lambda turns that
into the fallback. That reply scored 0.00 on grounding and got blocked, so
the grounding check now runs only on real answers. Telling the model to
match the question's language didn't hold up, so a short list of Filipino
words picks English or Taglish in code. Masked ID numbers get a note to
ignore them. Banned strings in the eval are checked in code, after Nova Pro
misjudged them twice. Correct answers went from 6/12 to 10/12.

## 2026-10-27: samconfig.toml was pinning guardrail version 1
Plain `sam deploy` uses the parameters saved in samconfig.toml, which still
said version 1, so some deploys quietly went back to the old guardrail. I
now update .env and samconfig.toml together for every new version. The v0.2
run may have used version 1.