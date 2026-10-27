"""Send every eval question to the live API and save the raw replies.

Usage: python evals/run_eval.py v0.1
Needs ASK_URL set to the /ask endpoint.
"""

import json
import os
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent


def ask(url, question):
    request = urllib.request.Request(
        url,
        data=json.dumps({"question": question}).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    started = time.time()
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read())
    body["seconds"] = round(time.time() - started, 2)
    return body


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "run"
    url = os.environ.get("ASK_URL")
    if not url:
        sys.exit("Set ASK_URL first.")

    questions = yaml.safe_load((HERE / "questions.yaml").read_text())
    out = HERE / "runs" / f"{date.today()}-{label}.jsonl"
    out.parent.mkdir(exist_ok=True)

    with out.open("w") as f:
        for q in questions:
            try:
                reply = ask(url, q["question"])
            except Exception as error:  # keep going, the report shows the gap
                reply = {"error": str(error)}
            f.write(json.dumps({"id": q["id"], **reply}, ensure_ascii=False) + "\n")
            print(q["id"], "ok" if "error" not in reply else reply["error"])
            # The API is throttled at 5 requests a second. No need to push it.
            time.sleep(0.5)

    print(f"saved {out.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
