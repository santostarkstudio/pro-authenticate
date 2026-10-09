# Candidate privacy: how the application protects candidates

**Goal:** a candidate is visible only to the people who must see them, only while needed, and never to other candidates or the public.

## Who sees what
| Data | Candidate | Interviewer | Reviewer | Owner | Other candidates | Public |
|---|---|---|---|---|---|---|
| Own video and answers | yes (own) | yes | via evidence only | yes | **no** | **no** |
| Name | yes (own) | yes | **hidden** ("Candidate 12") | yes | **no** | **no** |
| Verdicts, scores, notes, wide view | **no** | yes | yes | yes | **no** | **no** |
| Interview page for a code | name of the interview only | full | full | full | name only | name only |
| Audit log | no | yes | yes | yes | no | no |

## What the server enforces (not just the page)
- **Rooms:** a candidate's video, chat and answers go to staff only. Staff messages reach a candidate only when addressed to that person. Messages sent to candidates never contain names or ids. (`backend/app/rooms.py`, tested.)
- **Blind review:** the Reviewer role sees "Candidate N" instead of names. (`privacy.py`, tested.)
- **Short-lived tickets** for live connections, so no long-lived token appears in a web address that could be logged. (`Tickets`, tested.)
- **No caching** of API responses, `no-referrer`, frame blocking, and a camera permission limited to the site's own origin.
- **Longer interview codes** (10 characters) and limits on guessing and joining.
- **No raw frames stored by default.** Frames are saved only when an interviewer saves evidence or recording is on.
- **Erase and retention:** the owner can erase one candidate completely (`DELETE /api/candidates/{id}`), and candidates are erased automatically after `FG_RETENTION_DAYS` (default 90). The audit log keeps only that an erasure happened.
- **Notice:** the join screen tells the candidate about recording, automatic checks, that the interviewer can enlarge the video, and that other candidates never see them.

## Honest limits
- The single-file demo keeps all data in one browser, so anyone using that same browser can read it. **Only the backend version enforces these rules.** Use the backend for any real candidate.
- A candidate can record their own screen. No web page can prevent that.
- Staff are trusted people. The audit log shows what they did, but cannot stop misuse. Give staff the least access they need and review the audit log.
- Face and voice data are sensitive personal data. India's DPDP Act, 2023 applies: get legal review of the consent text, the retention period, and the process for candidates who ask for their data to be deleted.

## Still to build for the strongest protection
Encrypt stored recordings and evidence, signed expiring links for any file download, two-factor sign-in for staff, per-interview staff access (so a reviewer sees only their interviews), and a candidate "request my data / delete my data" page.
