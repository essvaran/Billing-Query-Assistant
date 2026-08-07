---
article_id: HC-BILL-001
product_area: billing-migration
last_updated: 2026-06-01
---

# Billing Profile Migration Overview

## What Is Billing Profile Migration?

Billing profile migration moves your billing profile — payment methods, invoice
history, tax information, and subscription entitlements — from the legacy
billing platform to the new billing platform. Migration happens automatically
for most accounts, but some accounts require the account owner to confirm the
migration before it completes.

Migration runs in three stages: **queued**, **in progress**, and
**completed**. You can check your current stage on the Billing Overview page
under Account Settings.

## Who Needs to Take Action

Most accounts migrate with no action required. You only need to take action if
your account uses any of the following:

- A payment method added before 2024 that was never re-verified.
- More than one billing contact on the account.
- A custom invoice template.

If any of these apply, you will see a banner labeled "Action required before
migration" on the Billing Overview page.

## Migration Prerequisites

Before migration can start, the following must be true:

1. The account has at least one verified payment method.
2. There are no unresolved disputed charges on the account.
3. The account owner has accepted the updated billing terms.

If any prerequisite is not met, migration is queued indefinitely until the
condition is resolved. This is the most common cause of a migration that
appears "stuck" in the queued stage.

## Timeline

Migration for a single account typically completes within 24 hours of all
prerequisites being met. Accounts with more than 50 historical invoices may
take up to 72 hours because invoice history is re-indexed during migration.

## Related Articles

See "Billing Migration Error Codes and Fixes" for troubleshooting specific
error codes, and "Migration Rollback and Support Escalation" if migration
fails and needs to be reversed.
