# Review system (Claude ↔ ChatGPT)

This folder lets ChatGPT review Claude's work on CrashLens, and lets Claude respond
to every finding, without anyone pretending a review happened when it didn't.

## The rule

**A change counts as reviewed only when a real review file exists in `reviews/`.**
Claude never writes files into `reviews/` and never marks anything as reviewed by
ChatGPT on its own. If `reviews/` is empty, nothing has been reviewed yet.

## Files

| File | Who writes it | Purpose |
|---|---|---|
| `TASKS.md` | Claude and you | Shared task queue: what's planned, in progress, done |
| `REVIEW_GUIDE.md` | Claude | What reviewers should check and how strict to be |
| `REVIEW_TEMPLATE.md` | Claude | The exact answer format ChatGPT is asked to use |
| `packets/` | script | Generated review packets (not committed) |
| `reviews/` | **ChatGPT only** (saved by you or by the API script) | Real review reports |
| `RESPONSES.md` | Claude | Claude's answer to every finding: addressed / declined / deferred |
| `LAST_REVIEWED` | you / Claude after a review is processed | Commit the last review covered |

## How a review round works

1. **Make a packet** (from the project folder):
   ```
   python scripts/make_review_packet.py          # changes since LAST_REVIEWED
   python scripts/make_review_packet.py --all    # whole project (first review)
   ```
   This writes `review/packets/packet-<commit>.md` (split into parts if large).
   It refuses to create a packet if the secret scanner finds anything key-like.

2. **Give it to ChatGPT**, either:
   - **By hand:** open ChatGPT, attach or paste the packet file(s), send. Save
     ChatGPT's full answer as `review/reviews/<date>-<commit>.md`.
   - **Automatically (optional):** set `OPENAI_API_KEY` and `OPENAI_MODEL` as
     environment variables on your PC (never in a file in this repo), then run
     ```
     python scripts/request_chatgpt_review.py review/packets/packet-<commit>.md
     ```
     The answer is saved with the model name and API response id at the top.

3. **Tell Claude** a review has arrived (or Claude finds it at the start of a work
   session). Claude reads it, fixes what's right, and records every finding in
   `RESPONSES.md`:
   ```
   - [R-2026-11-09-1] addressed in abc1234 - wrapped the read in try/except
   - [R-2026-11-09-2] declined - IPv4 redaction removed on purpose, see redact.py
   ```

4. **Check what's open:**
   ```
   python scripts/review_status.py
   ```

5. Update `LAST_REVIEWED` to the commit the review covered, so the next packet
   only contains newer changes.
