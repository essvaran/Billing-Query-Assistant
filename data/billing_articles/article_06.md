---
article_id: HC-BILL-006
product_area: billing-migration
last_updated: 2026-06-20
---

# Migration Rollback and Support Escalation

## When a Rollback Is Possible

A billing profile migration can be rolled back to the legacy platform only if
the migration has not yet reached the **completed** stage. Once a migration
reaches completed status, it cannot be rolled back, because invoice numbering
and tax records have already switched to the new platform's format.

## Rollback-Related Error Codes

| Error code | Cause | Fix |
|---|---|---|
| ERR-6001 | Rollback was requested after the migration already reached completed status | Rollback is not available; contact billing support for a manual correction instead |
| ERR-6015 | Rollback failed because the legacy billing profile was already archived | Contact billing support to restore the archived legacy profile before retrying rollback |
| ERR-6030 | Rollback was requested by a user without the Billing Administrator role | Ask an Account Owner or Billing Administrator to submit the rollback request |

## How to Request a Rollback

1. Go to the Billing Overview page.
2. Select "Request rollback" under Migration Status.
3. Provide a reason for the rollback request.

Rollback requests are processed within 4 business hours while migration is
still in the queued or in-progress stage.

## Escalating to Support

Escalate to billing support when:

- The same migration error code recurs after two retry attempts.
- A rollback request fails with ERR-6015.
- Migration has been stuck in the queued stage for more than 72 hours.

When escalating, include the account ID, the exact error code, and the
migration stage shown on the Billing Overview page. Support cannot look up
your account without the account ID.

## Support Response Time

Escalated migration issues receive a first response within one business day.
This article does not define a guaranteed resolution time or compensation
for migration delays; no such commitment exists for migration-related
support cases.
