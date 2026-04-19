import sys
import urllib.request

doc_id = sys.argv[1] if len(sys.argv) > 1 else "2de224a5-9511-407e-a675-1daa02c190a3"
body = (
    urllib.request.urlopen(f"http://127.0.0.1:3001/documents/{doc_id}/build", timeout=30)
    .read()
    .decode("utf-8", "replace")
)
print("LEN", len(body))
for key in ["data-msg", "Error:", 'error"', "TypeError", "Agent runtime", "Build State", "Kickoff", "Loading"]:
    idx = body.find(key)
    if idx >= 0:
        start = max(0, idx - 50)
        print(f"  {key!r} @ {idx}: {body[start : idx + 200]!r}")
