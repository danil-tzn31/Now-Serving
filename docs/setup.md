# Setup

How I set up the AWS side of Now Serving. Everything is in us-east-1.
The Lambda and API come later and are deployed with SAM (see template.yaml).

## Before you start
- Signed in as an IAM user, not root. Bedrock won't create a Knowledge
  Base as root (I found this out the hard way).
- Console region set to N. Virginia. Always check the URL, should be us-east-1.

## S3 bucket
- Bucket: nowserving-articles-<initials>, versioning on, public access blocked
- Articles go under articles/, uploaded by scripts/sync_articles.sh
- Only articles marked `status: verified` are uploaded

## Knowledge Base
| Setting | Value | Why |
| --- | --- | --- |
| Type | Unstructured, vector store | Articles are plain Markdown |
| Embeddings | Titan Text Embeddings V2, 1024 | [your reason, e.g. Amazon model, cheap] |
| Vector store | S3 Vectors (quick create) | [OpenSearch Serverless costs ~$350/month] |
| Chunking | Fixed size, 300 tokens, 15% overlap | [starting point, will compare later] |

Re-sync after editing articles:
    ./scripts/sync_articles.sh
Needs BUCKET, KB_ID and DS_ID in a local .env (not committed).

## Guardrail
- Denied topics: fixers, fake documents, legal disputes
- PII: email, phone, PH mobile numbers and 12–16 digit ID numbers.
  Masked on input, detect only on output so hotline numbers in answers
  aren't hidden.
- Contextual grounding: grounding 0.7, relevance 0.5, both block
- 
## First retrieval test (no model, Generate responses off)
| Question | Top article | Score |
| --- | --- | --- |
| What do I need to renew my passport? |passport-renewal-adult | 0.62 |
| pano mag-renew ng passport |passport-renewal-adult | 0.76 |
| magkano birth certificate sa psa | psa-birth-cert-in-person | 0.66 |
| Can my sister claim my passport? | passport-claiming| 0.49 |
| How do I get an NBI clearance? |passport-new-adult | 0.38 |

Taglish beats English queries. Model sources out the right articles. 

## Costs so far
No billing alerts for now