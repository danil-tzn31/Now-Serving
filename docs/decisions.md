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
