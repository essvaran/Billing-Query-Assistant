---
article_id: HC-BILL-002
product_area: billing-migration
last_updated: 2026-06-05
---

# Billing Migration Error Codes and Fixes

## Overview

This article lists the error codes that can appear while a billing profile is
being migrated to the new billing platform, what each code means, and the
recommended fix.

## Error Codes

| Error code | Cause | Fix |
|---|---|---|
| ERR-4032 | Billing profile migration is incomplete because a required field was not carried over from the legacy platform | Reconnect the billing profile and retry the migration from the Billing Overview page |
| ERR-4040 | The legacy payment method on file could not be re-verified with the card network | Add a new payment method and set it as default before retrying migration |
| ERR-4155 | Migration was queued but a duplicate billing profile already exists for this account | Contact billing support to merge the duplicate profile before retrying |
| ERR-5010 | The invoice account is locked because of a prior unresolved dispute | Ask an account administrator to resolve the dispute, then unlock the invoice account |
| ERR-5020 | Tax identification data could not be transferred because it was stored in an unsupported legacy format | Re-enter tax identification information manually on the new billing platform |

## How to Read This Table

Each row is independent. A single migration attempt can surface more than one
of these codes if multiple conditions are unmet at the same time. Codes in the
4xxx range are migration-blocking and must be fixed before migration can
proceed. Codes in the 5xxx range indicate the migration completed but with a
restricted account state that needs manual resolution.

## Retrying After a Fix

After applying a fix, retry migration from the Billing Overview page. Retries
do not create a new migration record; the existing migration record is
updated in place, so migration history remains accurate for support purposes.

## When to Escalate

If the same error code recurs after two retry attempts, do not keep retrying.
Escalate to billing support with the error code and the account ID. See
"Migration Rollback and Support Escalation" for the escalation process.
