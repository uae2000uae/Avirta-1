# Avirta Deploy & Concurrency Notes

This explains why deploys sometimes conflict (the ETag `ABORTED` error) and why a
deploy during a live game resets the game — plus the workflow to avoid both.

## Background: why a deploy resets games

`cloudbuild.yaml` pins the service to one instance (`--min-instances=1
--max-instances=1`) because **game state lives in the instance's memory and local
filesystem**, which is not shared across instances. A deploy creates a **new
revision = a fresh container**; traffic cuts over to it and the old container is
drained and killed, so its in-memory game rooms disappear. Polling clients then
hit the new instance, get "room not found," and the game closes. Session affinity
does not carry across revisions, so it cannot prevent this.

The permanent fix is to move game state to Firestore/Redis (option **D**, not yet
done). Until then, use the workflow below to avoid interrupting live games.

---

## A. Question-data pushes no longer trigger deploys

The app auto-pushes question JSON to GitHub on edits (and on game end/reset). If
the Cloud Build trigger deploys on every push, those data pushes cause deploys —
which can kill other live games. Fix: tell the trigger to ignore
`contents/questions/**` so a push that only changes question data is skipped.
Pushes that also change code still deploy normally.

```bash
# Linux / Cloud Shell
./configure-deploy-trigger.sh <TRIGGER_NAME>
```
```bat
:: Windows
configure-deploy-trigger.bat <TRIGGER_NAME>
```

Run with no arguments to list your triggers. Set `REGION` if your trigger isn't
in `us-central1` (or empty for a global trigger). The script exports the trigger,
adds `contents/questions/**` to `ignoredFiles`, and re-imports it.

**Console alternative:** Cloud Build → Triggers → edit your trigger → *Ignored
files filter* → add `contents/questions/**` → Save.

---

## B. The IAM ETag `ABORTED` error is fixed

```
ERROR: (gcloud.beta.run.services.add-iam-policy-binding) ABORTED: There were
concurrent policy changes ... ETag ... did not match the current policy's ETag
```

This came from an explicit `add-iam-policy-binding` call that ran on every deploy
— in **two** places: `Direct deploy.bat` (manual deploys) and, more importantly,
`cloudbuild.yaml` step 2 (the Cloud Build trigger, i.e. every push-triggered
deploy). That binding is **already applied** by the `--allow-unauthenticated`
flag on `gcloud run deploy`, so the extra call was redundant and, when two builds
overlapped, raced on the IAM policy and ABORTed. The redundant step has been
removed from **both** `Direct deploy.bat` and `cloudbuild.yaml`. Because the
trigger reads `cloudbuild.yaml` from the pushed commit, the fix applies on the
next build.

If you ever deploy **without** `--allow-unauthenticated` and need to grant public
access once, run manually:

```bash
gcloud run services add-iam-policy-binding avirta \
  --region=us-central1 --member=allUsers --role=roles/run.invoker
```

---

## C. Deploy without interrupting live games (no-traffic workflow)

Instead of the immediate-cutover `Direct deploy.bat`, ship the new revision with
**0% traffic**, verify it on its preview URL, then flip traffic when it's quiet.

```bash
# 1) Deploy the new revision with no traffic (live games keep running)
./deploy-no-traffic.sh          # Windows: deploy-no-traffic.bat

# 2) Test the printed "next" preview URL

# 3) Flip 100% traffic to it during a lull (this ends games on the old revision)
./promote-latest.sh             # Windows: promote-latest.bat
```

The cutover in step 3 still drains the old revision, so promote when no games are
active (or accept a brief interruption). Only option **D** removes that entirely.

---

## Which script to use

| Situation | Use |
|-----------|-----|
| Normal deploy, nobody playing | `Direct deploy.bat` (immediate cutover) |
| Deploy while people may be playing | `deploy-no-traffic.*` then `promote-latest.*` during a lull |
| Question data changed only | Nothing — pushes are auto-synced and (after A) don't deploy |
| Grant public access once (rare) | manual `add-iam-policy-binding` (see B) |

## D. Permanent fix (future)

Move game rooms from in-memory/local-disk to Firestore (see
`datastore/firestore_backend.py`) or Memorystore/Redis, and make the client's
poll loop retry on a transient "room not found" instead of closing the game. Then
a redeploy — or running multiple instances — no longer drops games, and the
`--min-instances=1 --max-instances=1` pin in `cloudbuild.yaml` can be removed.
