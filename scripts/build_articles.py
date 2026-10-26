"""Copy verified articles into build/ with the metadata files Bedrock reads."""

import json
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ARTICLES = ROOT / "articles"
BUILD = ROOT / "build" / "articles"

# Only these fields go to Bedrock. S3 Vectors keeps filterable metadata small,
# so the aliases stay out (they're already in the article body anyway).
KEEP = ["id", "title", "service", "agency", "task", "last_checked"]


def split_front_matter(text):
    if not text.startswith("---"):
        return None, text
    _, header, body = text.split("---", 2)
    return yaml.safe_load(header), body.lstrip()


def main():
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)

    copied, skipped = 0, []
    for path in sorted(ARTICLES.glob("*/*.md")):
        meta, body = split_front_matter(path.read_text(encoding="utf-8"))
        if not meta or meta.get("status") != "verified":
            skipped.append(path.name)
            continue

        # Retrieval only searches the body text, so the aliases go into
        # the body too. Otherwise "pa-renew ng passport" may not match anything.
        aliases = ", ".join(meta.get("aliases", []))
        intro = f"Also asked as: {aliases}\n\n" if aliases else ""

        out = BUILD / path.parent.name / path.name
        out.parent.mkdir(exist_ok=True)
        out.write_text(intro + body, encoding="utf-8")

        attrs = {key: str(meta[key]) for key in KEEP if key in meta}
        attrs["source_url"] = meta["source_urls"][0]
        sidecar = out.with_name(out.name + ".metadata.json")
        sidecar.write_text(json.dumps({"metadataAttributes": attrs}, indent=2))
        copied += 1

    print(f"{copied} articles ready in build/articles")
    if skipped:
        print("skipped (not verified):", ", ".join(skipped))
    return 0 if copied else 1


if __name__ == "__main__":
    sys.exit(main())
