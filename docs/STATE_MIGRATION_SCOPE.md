# State Migration Scope — Moving Off In-Memory / JSON Storage

**Status:** Draft for review
**Author:** Engineering
**Date:** 2026-07-04
**Related:** `cloudbuild.yaml` (`--max-instances=1` stopgap), `.junie/docs/tasks.md` (High Priority → "Implement Proper Database Layer")

---

## 1. Problem statement

Avirta runs on Cloud Run but keeps its live and durable state on a single
instance's memory and local filesystem:

- **Live game state** lives in the module-level dict `game_rooms = {}` in
  `app.py`. It only exists in the process that created the room.
- **Durable data** (question bank, reported questions, admin settings, AI
  batches, game-event logs) is read/written as JSON files under
  `contents/` and `questionmanagement/`.

Cloud Run instances are ephemeral and horizontally scaled. This design breaks
in three ways the moment more than one instance exists:

1. **Split-brain multiplayer.** Two players in the same room can be routed to
   different instances, each with its own `game_rooms` copy, and see divergent
   state. Session affinity reduces but does not eliminate this (affinity is
   best-effort and lost on instance recycle).
2. **Silent data loss.** New/edited questions and reported questions written to
   the local filesystem vanish on scale-down or redeploy, and are invisible to
   other instances.
3. **No durability guarantees.** A crash or routine redeploy drops every active
   game.

We are currently masking this with `--min-instances=1 --max-instances=1`
(see `cloudbuild.yaml`). That caps throughput at one container and still loses
active games on every deploy. This document scopes the real fix.

---

## 2. Current-state inventory

| Data | Where it lives today | Access pattern | Durability need |
|------|----------------------|----------------|-----------------|
| Active game rooms | `game_rooms` dict + `GameStatusManager.save_game_room()` → `contents/game_events/rooms/*.json` | High read/write during a game; per-room | Ephemeral-ish (must survive redeploy while a game is live) |
| Game event log / feed | `GameStatusManager` → `contents/game_events/events/*` (append JSONL) | Written on every event; polled every 1s by clients | Short-lived, but must be shared across instances |
| Question bank | `contents/questions/*.json` (32 files) | Read-heavy; occasional writes (add/edit/import) | Durable, canonical |
| Reported questions | `questionmanagement/reported_questions/R*.json` | Low volume write; admin reads | Durable |
| Admin / game settings | `contents/admin_controls/*.json` | Rare writes, frequent reads | Durable |
| AI-generated batches | `questionmanagement/ai_generated_questions/` | Write on generation, read in history | Durable |
| Session data | Signed cookie (Flask default): `player_name`, `room_id`, `current_question`, `admin_authenticated`, etc. | Per request | OK across instances **iff** `SECRET_KEY` is shared (already flagged) |

Notable coupling to fix along the way:
- `current_question` is stored **in the cookie** (`app.py` lines ~347, 841, 869,
  943). It should move server-side once room state is centralized, to keep the
  cookie small and authoritative.
- `GameStatusManager` already abstracts persistence behind
  `save_game_room()` / `load_game_room()` / event methods — this is the natural
  seam to swap the backend.

---

## 3. Goals & non-goals

**Goals**
- Any instance can serve any request for any room with consistent state.
- Question bank and reported questions are durable and shared.
- Remove the `--max-instances=1` stopgap; support autoscaling.
- Keep the current UX (question types, tools, leaderboard) unchanged.

**Non-goals (this phase)**
- Rewriting gameplay logic or the question schema.
- User accounts / auth overhaul (tracked separately).
- Full observability/metrics stack.

---

## 4. Options considered

### A. Firestore (Native mode) — recommended primary
- Serverless, no capacity planning, scales with Cloud Run, generous free tier.
- Document model maps cleanly onto rooms, questions, reports, batches.
- **Real-time listeners** can replace the 1s polling feed directly (client
  subscribes to the room doc / events subcollection).
- Strong-enough consistency for this workload; transactions available for
  turn/score updates.
- Cons: query model is limited vs SQL; write cost on very chatty event streams
  (mitigate by batching events).

### B. Cloud SQL (PostgreSQL)
- Best if we want rich relational queries/reporting on the question bank.
- Cons: always-on instance cost, connection management from Cloud Run
  (needs the connector / pooling), no built-in realtime — still need SSE/Redis.

### C. Memorystore (Redis)
- Ideal for **hot, transient** room state and a pub/sub fan-out for realtime.
- Cons: not durable on its own (needs AOF/snapshot), VPC connector required,
  another managed component. Overkill if Firestore listeners suffice.

### D. GCS (JSON blobs)
- Smallest change (swap file paths for object paths). Shared across instances
  and durable.
- Cons: no locking/transactions, no realtime, poor for high-frequency room
  writes. Acceptable only for the low-churn durable stores (question bank,
  reports) as an interim step.

**Recommendation:** Firestore-first. Use Firestore for both durable data and
live room/event state, and use Firestore real-time listeners to replace
polling. Revisit Redis only if event write volume or latency proves Firestore
too chatty/expensive under load.

---

## 5. Target architecture (Firestore-first)

```
Cloud Run (N instances, stateless)
        │
        ├── Firestore
        │     rooms/{roomId}                 ← room state doc (players, turn, board)
        │     rooms/{roomId}/events/{eventId}← append-only event feed
        │     questions/{questionId}         ← question bank (migrated from JSON)
        │     categories/{categoryId}
        │     reports/{reportId}             ← reported questions
        │     ai_batches/{batchId}
        │     settings/{docId}               ← admin/game settings
        │
        └── Secret Manager: SECRET_KEY (shared cookie signing) + existing tokens
```

- **Sessions:** keep Flask signed-cookie sessions, but move `current_question`
  and any per-turn state into the room doc; the cookie holds only identifiers
  (`player_name`, `room_id`). Requires the shared `SECRET_KEY` secret (already
  scoped in the security pass — just needs the secret created and wired in
  `cloudbuild.yaml`).
- **Realtime:** replace `setInterval(pollGameUpdates, 1000)` in
  `static/js/livestatus.js` with a Firestore `onSnapshot` subscription to the
  room doc + events subcollection. Fallback: keep polling behind a feature flag
  during rollout.

---

## 6. Data-model mapping (starting point)

- `rooms/{roomId}`: `{ name, host, players[], current_player, board, question_types,
  categories, status, question_active, current_question, updated_at }`
- `rooms/{roomId}/events/{autoId}`: `{ type, player, payload, ts }`
  (batch writes; TTL policy to expire finished-room events).
- `questions/{id}`: existing per-question fields from the JSON files, plus
  `category`, `type`, `difficulty`, `active`, `use_count`, `created_at`.
- `reports/{id}`: current reported-question schema.
- `settings/game`, `settings/ai`, `settings/api`: current JSON settings docs.

Add composite indexes for the common reads already noted in `tasks.md`:
`category+active`, `type+difficulty`, `created_at`.

---

## 7. Migration plan (phased, each shippable independently)

**Phase 0 — Prep (no behavior change)**
- [ ] Add `google-cloud-firestore` to `requirements.txt`.
- [ ] Create a `datastore/` abstraction layer with interfaces:
      `RoomStore`, `QuestionStore`, `ReportStore`, `SettingsStore`.
- [ ] Provide two implementations per interface: `JsonFileStore` (current) and
      `FirestoreStore`, selected by env var `STATE_BACKEND=json|firestore`.
- [ ] One-time export/import script: JSON files → Firestore collections.

**Phase 1 — Durable data first (lowest risk)**
- [ ] Move question bank, reported questions, settings, AI batches to Firestore.
- [ ] Cut reads/writes over via the `QuestionStore`/`ReportStore` interfaces.
- [ ] Backfill script + verification (counts + spot-check).
- These stores are low-churn, so correctness is easy to validate.

**Phase 2 — Live room state**
- [ ] Back `GameStatusManager.save_game_room/load_game_room` and event
      methods with Firestore (swap the file I/O at lines ~248, 568, 624).
- [ ] Remove reliance on the in-process `game_rooms` dict as the source of
      truth (treat it as a per-request cache only, or drop it).
- [ ] Move `current_question` out of the cookie into the room doc.

**Phase 3 — Realtime**
- [ ] Replace 1s polling with Firestore `onSnapshot` in `livestatus.js`
      (feature-flagged; polling remains as fallback).
- [ ] Load-test event write volume; batch events if needed.

**Phase 4 — Scale out**
- [ ] Create the `SECRET_KEY` secret and wire it in `cloudbuild.yaml`
      (`SECRET_KEY=SECRET_KEY:latest`).
- [ ] Remove `--min-instances=1 --max-instances=1`; set a sane
      `--max-instances` and concurrency.
- [ ] Soak test with multiple instances and 2+ players per room.

---

## 8. Effort & sequencing (rough)

| Phase | Est. effort | Risk | Unblocks |
|-------|-------------|------|----------|
| 0 Prep + abstraction | 2–3 days | Low | everything |
| 1 Durable data | 2–3 days | Low | data loss fix |
| 2 Live room state | 4–6 days | Medium | multi-instance correctness |
| 3 Realtime listeners | 3–5 days | Medium | drops polling cost |
| 4 Scale out | 1–2 days | Low | removes stopgap |

Total: ~2–3 weeks of focused work. Phases 0–1 already remove the **data-loss**
class of bugs and can ship on their own.

---

## 9. Risks, testing, rollback

- **Risk: dual-write drift during migration.** Mitigate with the backend flag —
  never write to both; cut over per store, verify, then delete the JSON path.
- **Risk: Firestore cost from chatty events.** Mitigate with event batching and
  TTL cleanup of finished rooms; measure in Phase 3 before removing polling.
- **Testing:** the new `tests/` suite (added in the security pass) should gain
  store-level unit tests plus an integration test using the Firestore emulator
  in CI. Keep the `JsonFileStore` implementation as a fast, offline test double.
- **Rollback:** each phase is guarded by `STATE_BACKEND`; flipping it back to
  `json` restores prior behavior (with the max-instances stopgap) instantly.

---

## 10. Exit criteria

- No game state or question data lives on a local filesystem or in a
  per-instance dict as the source of truth.
- The app runs correctly with `--max-instances > 1` and 2+ players per room
  across instances.
- The 1s polling loop is removed (or feature-flagged off) in favor of realtime
  listeners.
- `SECRET_KEY` is sourced from Secret Manager so sessions survive restarts and
  are valid on every instance.
