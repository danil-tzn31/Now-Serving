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
