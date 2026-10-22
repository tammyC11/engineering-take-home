# Notes

Time spent: _(fill in)_

Status markers below: ✅ built and tested · 🚧 planned, not built yet.

## Assumptions and open questions

**Time zones: "the days as they see them in their diary"**

- The brief (Dr. Keller) says a shared period means the patient's days in "their own time zone",
  but nothing defines which time zone that is. The backend only knows `patients.timezone`
  (IANA name); the app knows the device time zone and never sends it.
- **Assumption:** `patients.timezone` is the patient's own time zone. When a share is created,
  that time zone is copied onto the share, and the period is read in it from then on.
- **Known gap:** the app groups the diary by the *device's* local time (`dayOf()` → `toLocal()`
  in `app/lib/format.dart`), not by `patients.timezone`. If the two differ (travel, a move
  without a profile update), entries near midnight can sit on one day in the patient's diary and
  on another day in the shared period. Nothing in the app or API lets the patient set their time
  zone today. See next steps.
- **`app-v1` entries** (Tom): their `recorded_at` is local wall-clock time stored as if it were
  UTC. When deciding whether such an entry falls inside a shared period, its stored date and time
  are read as the patient's local time, not converted. The rows themselves are not changed: that
  would be a migration on health data and would change what `/entries` returns to app v2.3.
- **Related finding, not fixed:** the patient's own diary shows `app-v1` entries at the wrong
  time already, because the app converts their fake-UTC timestamp to local time again. The seed
  entry at 23:50 on 14 March shows as 00:50 on 15 March in Berlin, the exact case Dr. Keller
  described.

**Not revealing who is a patient (Selin)**

- `GET /clinician/patients/{patient_id}/entries` returns exactly the same `404 {"detail": "Not
  found"}` in every case where the doctor may not read. That covers: patient doesn't exist, never
  shared, shared with another doctor, share revoked, share expired or not started yet. Otherwise
  a doctor could loop over the sequential IDs and list who our patients are.
- A doctor with an active share whose period has no entries gets `200 []`. That reveals nothing
  new: the patient told this doctor themself by sharing.
- No patient data in responses beyond the entries, and no patient IDs in metrics or logs.
- **Why not UUIDs?** They would make guessing IDs hard (defence in depth), but they don't fix the
  leak itself: a doctor can already hold a real ID (an old share, a referral letter). The
  responses have to look the same either way. API.md also fixes the IDs as integers and `/me`
  must not change, so a public UUID is a next step, not part of this change.

**Overlapping shares with the same doctor**

- Each share stands on its own. For each entry, a doctor sees the note if *any* active share
  covering that entry's day has `include_notes`. Revoking a share removes exactly what it
  granted.
- Rejected alternatives: "newest share wins" (creating a share would silently change an older
  consent) and "refuse overlaps" (API.md defines only `422` for invalid input, and refusing a
  valid request would annoy patients).
- To avoid confusing the patient (see the app section below), the app shows a warning before a
  new share overlaps an active one with the same doctor. It also groups shares by doctor, with a
  plain summary of what each doctor can see.

**Other assumptions**

- A share's period may lie in the past or the future. Only `from_date > to_date` is invalid
  (`422`). An unknown `clinician_id` is invalid input (`422`).
- Revoking a share that is already revoked returns it unchanged (`200`). Revoking another
  patient's share, or one that doesn't exist, returns `404`.
- Only reads that returned at least one entry are recorded in the access log. An empty answer
  disclosed no health data.
- Consent wording is versioned in code (a `consent_version` string stored on each share); the
  text itself lives in the repo.

## Data model decisions

Migration `backend/alembic/versions/0002_shares_and_access_log.py` ✅, models in
`backend/app/models.py` ✅, tests in `backend/tests/test_schema.py` ✅.

`diary_entries`, `patients` and `clinicians` are unchanged. `/entries` and `/me` keep their exact
shape for app v2.3.

**`shares`**: one row per consent.

| Column | Why |
| --- | --- |
| `patient_id` → patients, `clinician_id` → clinicians | Who shares with whom |
| `from_date`, `to_date` (`date`, inclusive, `CHECK from_date <= to_date`) | The patient agrees to calendar days, not timestamps |
| `timezone` | Copied from the patient when sharing, so a later profile change can't widen or shift the consent (O.Cons_1) |
| `include_notes` (default `false`) | Notes stay private unless the patient opts in (Selin, Dr. Keller) |
| `consent_version` | Which wording the patient agreed to (O.Cons_3) |
| `created_at`, `revoked_at` | Revoking sets a timestamp; shares are never deleted, because they are the proof of consent behind each access record |

Index on `(clinician_id, patient_id)` for the doctor's lookup. `timezone` and `consent_version`
are internal and not returned, because the API.md response shape is fixed.

**`access_log`**: one row per doctor read that returned entries.

| Column | Why |
| --- | --- |
| `patient_id` (no foreign key) | Whose diary was read; no FK so the record can outlive erasure |
| `clinician_id` → clinicians | Who read it; `clinician_name` in the response comes from joining `clinicians` |
| `accessed_at` | When (O.Log_1) |
| `entry_ids` (`int[]`, no FK) | Exactly which entries were disclosed |
| `notes_shown` | Whether notes were part of what was disclosed |

- **Append-only (O.Log_3):** a Postgres trigger rejects every `UPDATE` and `DELETE`. `TRUNCATE`
  stays possible so the test suite can reset tables; production would also deny it, and grant
  the app's database role only `INSERT` and `SELECT` on this table.
- 🚧 The log row is written in the same transaction as the read. If the write fails, the doctor
  gets no data and a failure counter goes up (O.Mon_1). No data leaves without a record.

## Requirements

| ID | Applies? | Where it is met (code, test), or why not |
| --- | --- | --- |
| O.Purp_1 | Yes | 🚧 App: a confirmation step before sharing shows the doctor, "mood and symptoms" (plus "notes" if chosen) and the period. Widget test. |
| O.Cons_1 | Yes | 🚧 Clinician endpoint returns only entries inside an active share's period, in the share's time zone; notes only if a covering share includes them. ✅ Time zone stored on the share. Tests for period edges, the `app-v1` case and notes. |
| O.Cons_2 | Yes | 🚧 `POST /shares/{id}/revoke` sets `revoked_at`; every read checks it. Test: a read after revoking returns 404. |
| O.Cons_3 | Yes | ✅ `shares.consent_version`. 🚧 Set from a constant on create; test. |
| O.Auth_1 | Yes, not met | Authentication is a stub, so the patient can't re-authenticate. How I would: put the last authentication time in the token, have `POST /shares` reject one older than 15 minutes with `401` and a "re-authenticate" code, and let the app ask for the password or biometrics and retry. |
| O.Pass_1 | No | This feature adds no passwords. |
| O.Log_1 | Yes | ✅ `access_log` table. 🚧 Every successful doctor read writes a row in the same transaction; test. |
| O.Log_2 | Yes | 🚧 `GET /access-log` and the app's "Who saw your diary" section; tests. |
| O.Log_3 | Yes, partly | ✅ Append-only trigger, tested in `test_schema.py`. Ten-year retention: nothing deletes these rows; a retention job and backup policy are outside this repo. |
| O.Log_4 | Yes | 🚧 **Existing violation:** `backend/app/main.py` logs every request body, which includes moods, symptoms and notes. Remove it; test that the log has no body. Metrics use only bounded labels, never patient IDs. |
| O.Mon_1 | Yes | 🚧 Counter for failed access-log writes, alerting on any increase (see Monitoring). |
| O.Err_1 | Yes | 🚧 The clinician endpoint returns one generic 404; FastAPI returns a generic 500 without a stack trace. Test that a failed log write returns no internal details. |
| O.Cryp_1 | Yes, outside this repo | Encryption at rest belongs to the database and disk setup (e.g. encrypted volumes, managed Postgres), not to application code. |
| O.Del_1 | Stretch goal, not built | See below. The schema is designed so erasure stays possible. |
| O.Doc_1 | Yes | This table. |

## Erasure (O.Del_1): how I would do it

Selin wants everything erased; Dr. Keller needs the record of which doctor saw what as clinical
evidence. Both can be met:

1. Delete the patient's `diary_entries`, then their `shares`, then the `patients` row, in one
   transaction. Foreign keys from those tables point at `patients`, so nothing is left behind.
2. Keep the `access_log` rows but pseudonymise them: replace `patient_id` with a keyed hash, so
   "Dr. X read 4 entries on 10 Oct" stays as evidence without saying whose they were. The log has
   no foreign keys to patients or entries, so step 1 doesn't touch it. `entry_ids` then point at
   entries that no longer exist, which is intended: they say what was disclosed, not what still
   exists.
3. The append-only trigger blocks step 2 for the normal app role. Erasure would run as a
   separate, audited database role that may only perform this update.
4. To decide with data protection and legal: the legal basis for keeping the pseudonymised
   records (likely the 10-year retention duty), and whether shares themselves must be kept as
   proof of consent in the same pseudonymised form.

## Monitoring

🚧 Planned; no labels ever carry a patient ID or name.

**Is sharing used, and do sharers keep logging? (Mara, in three months)**

- App events via `api.track()`: `share_created`, `share_revoked`, alongside the existing
  `entry_created`.
- Backend counters as a fallback that doesn't depend on the app sending events.
- Limitation: a Prometheus counter can't say whether *the patients who share* keep logging,
  because that needs per-patient data, which doesn't belong in metrics. For that I'd run a
  periodic query on the database (patients with a share vs without, entries per week before and
  after sharing) and report only the aggregate.

**Doctors can't open a diary (Lukas, on call)**

- `clinician_reads_total{outcome="ok|not_found|error"}` and the existing request latency
  histogram for that route.
- `access_log_write_failures_total`.
- Page someone right away: any access-log write failure (O.Mon_1; doctors get no data), or the
  5xx rate on the clinician route above a few percent for 5 minutes on weekday mornings.
- Can wait until morning: rising latency, or a jump in `not_found` (could be a portal bug, or
  someone probing IDs).
- When it's on fire: a Grafana panel per outcome, latency, and the API logs, which carry the
  route and status but no bodies.

## Screenshots

_(to add)_

## How I used AI

_(fill in)_ Claude Code to read the codebase and summarise it, to walk through BRIEF.md and
REQUIREMENTS.md, and to discuss the schema before coding. Decisions I made or changed during
that discussion: the uniform `404 "Not found"`; storing the time zone on the share; the warning
before a new share overlaps an existing one; grouping shares by doctor and using the existing
`created_at` ("Shared on …") so patients can find and revoke a share. I reviewed the generated
migration and models before moving on.

## Next steps

- Let the patient set their time zone in the app, and/or send the device time zone when
  sharing, so the shared days always match the diary view.
- Fix how the app displays `app-v1` entries (read their wall-clock time as local).
- A public, non-guessable patient ID for clinician-facing URLs, agreed with the portal team as a
  new endpoint version; keep integer primary keys internal.
- Rate-limit the clinician endpoint and alert on many `not_found` responses from one doctor.
- Re-authentication before sharing (O.Auth_1) once real authentication exists.
- Erasure as described above.
- A `consent_texts` table instead of a version string in code.
- Production database grants for `access_log` (`INSERT` and `SELECT` only, no `TRUNCATE`).
