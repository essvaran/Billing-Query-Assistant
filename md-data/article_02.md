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

---

## Payment Method Error Codes (PAY-Series)

These codes appear when the migration engine encounters a problem with a
payment method stored on the account. All PAY-series errors are blocking and
must be resolved before migration can proceed.

| Error code | Cause | Fix |
|---|---|---|
| PAY-1001 | Default payment method expired before migration completed | Update the card expiry or add a new card and set it as default |
| PAY-1002 | Card issuer declined a verification charge during token exchange | Contact your card issuer to allow the verification charge, then retry |
| PAY-1003 | ACH bank account routing number is invalid in the new platform's routing table | Update the bank account or add an alternative payment method |
| PAY-1004 | ACH micro-deposit verification has expired (older than 12 months) | Re-initiate micro-deposit verification in Billing > Payment Methods |
| PAY-1005 | Purchase order number has expired | Renew the PO or replace with a card payment method |
| PAY-1006 | Multiple payment methods share the same card number (likely duplicates) | Remove duplicate payment methods, keeping only the most recent |
| PAY-1007 | Payment method tokenization service returned a timeout during migration | Retry migration; if error persists after two retries, contact support |
| PAY-1008 | Card network reports the card as permanently blocked | Replace with a different payment method |
| PAY-1009 | Payment method is associated with a flagged fraud investigation | Account access is restricted; contact trust and safety team |
| PAY-1010 | Pre-paid balance is in a currency not supported by the new platform | Convert or withdraw the balance before migration; contact billing support |
| PAY-1011 | Payment method linked to a different account during migration deduplication | Remove the shared payment method and add it fresh to this account |
| PAY-1012 | SEPA direct debit mandate has not been signed | Re-sign the SEPA mandate under Billing > Payment Methods |
| PAY-1013 | PayPal billing agreement has been revoked | Re-authorize the PayPal billing agreement or use an alternative method |
| PAY-1014 | Corporate card issuer requires 3DS re-authentication every 90 days | Complete 3DS re-authentication in Billing > Payment Methods |
| PAY-1015 | Wallet credit balance is below the minimum threshold required for transfer | Top up the wallet balance to at least the minimum ($5.00 USD or equivalent) |

## Invoice and Billing History Error Codes (INV-Series)

INV-series codes indicate problems with the account's invoice history or
invoice configuration. Some INV codes are blocking (must fix before migration
can proceed); others are non-blocking (migration completes but with a
restricted state).

| Error code | Blocking | Cause | Fix |
|---|---|---|---|
| INV-2001 | Yes | Invoice record in an inconsistent state (debit and credit do not balance) | Contact billing support; do not retry until the inconsistency is resolved |
| INV-2002 | No | Invoice PDF generation failed for one or more historical invoices | Re-trigger PDF generation from Billing > Invoices > [Invoice] > Regenerate PDF |
| INV-2003 | Yes | Open invoice with a due date in the past and no payment on record | Pay or void the outstanding invoice before retrying migration |
| INV-2004 | No | Custom invoice template references a field that does not exist on the new platform | Update or delete the custom template; a default template is used until fixed |
| INV-2005 | No | Invoice sequence number gap detected in history (missing invoice number) | No action required; this is cosmetic and does not affect billing |
| INV-2006 | Yes | Consolidated invoice references child accounts that have not yet migrated | Wait for all child accounts to migrate before retrying the primary account |
| INV-2007 | No | Invoice currency mismatch between account settings and individual invoice records | Contact billing support to reconcile currency records |
| INV-2008 | No | More than 2,000 invoice line items on a single invoice; re-indexing may be slow | No action required; re-indexing completes automatically, usually within 6 hours |
| INV-2009 | Yes | Invoice drafted but never approved is blocking migration | Approve or delete the draft invoice before retrying |
| INV-2010 | No | Invoice attached document (such as a signed quote) could not be migrated | Re-upload attached documents from Billing > Invoices > [Invoice] > Attachments |

## Tax Error Codes (TAX-Series)

TAX-series errors relate to tax identification, exemption certificates, or
tax calculation configuration. Non-blocking TAX codes allow migration to
complete but restrict the account from generating new invoices until resolved.

| Error code | Blocking | Cause | Fix |
|---|---|---|---|
| TAX-3001 | No | Tax ID format is valid but could not be verified with the tax authority API | Re-enter the tax ID manually; the system will attempt re-verification |
| TAX-3002 | No | Tax exemption certificate expired before migration completed | Upload a renewed certificate in Billing > Tax Settings |
| TAX-3003 | No | Tax exemption certificate format not accepted by new platform (only PDF accepted) | Convert the certificate to PDF and re-upload |
| TAX-3004 | Yes | Tax ID conflicts with another account on the new platform | Contact billing support to resolve the tax ID conflict |
| TAX-3005 | No | Country-level tax configuration changed since the account was created; new settings required | Review and confirm tax settings in Billing > Tax Settings |
| TAX-3006 | No | State or provincial tax ID required for this jurisdiction but not on file | Add the required sub-national tax ID in Billing > Tax Settings |
| TAX-3007 | No | Legacy custom tax ID type cannot be automatically mapped; manual selection required | Go to Billing > Tax Settings and select the appropriate tax ID type |
| TAX-3008 | Yes | Tax record in the legacy system references a deleted product category | Contact billing support to re-map the tax category |
| TAX-3009 | No | GST registration status has changed since account creation; reverification required | Confirm GST registration status in Billing > Tax Settings |
| TAX-3010 | No | Reverse-charge VAT configuration is not supported in new platform's current region config | Contact billing support to manually configure reverse-charge settings |

## Subscription and Entitlement Error Codes (SUB-Series)

SUB-series errors occur when the migration engine cannot map a subscription
from the legacy platform to a valid plan on the new platform, or when an
entitlement record is in a state that blocks migration.

| Error code | Blocking | Cause | Fix |
|---|---|---|---|
| SUB-4001 | Yes | Legacy plan ID has no mapping to a new platform plan | Contact billing support; a plan migration specialist will assign the correct plan |
| SUB-4002 | Yes | Subscription is in a "payment failed" state from a failed renewal charge | Resolve the failed payment in Billing > Subscriptions before retrying |
| SUB-4003 | No | Add-on service is not available on the new platform | Contact sales to discuss equivalent add-ons on the new platform |
| SUB-4004 | No | Seat count on the legacy plan exceeds the maximum for the mapped new plan | Contact sales to adjust the plan tier or seat count |
| SUB-4005 | Yes | Subscription record has a pending cancellation that was not processed | Complete or cancel the cancellation workflow, then retry migration |
| SUB-4006 | No | Entitlement for a discontinued feature is still active; it will be deactivated | No action required; the feature will be removed from the account after migration |
| SUB-4007 | Yes | Subscription start date is in the future and is blocking plan validation | Wait until the subscription start date, then retry, or contact support |
| SUB-4008 | No | Promotional pricing applied to subscription has an end date in the past | No action required; standard pricing will apply on the next renewal |
| SUB-4009 | Yes | Subscription linked to an external reseller account that has not migrated | Coordinate with your reseller to ensure their account migrates first |
| SUB-4010 | No | Trial subscription converted to paid but trial flag not cleared in legacy | No action required; the trial flag is cleared during migration |

## Account and Profile Error Codes (ACC-Series)

ACC-series errors relate to the account profile itself — identity, ownership,
and account-level configuration — rather than billing data.

| Error code | Blocking | Cause | Fix |
|---|---|---|---|
| ACC-5001 | Yes | Account owner email address is not verified | Verify the account owner email before retrying migration |
| ACC-5002 | Yes | Account is flagged for deletion and cannot be migrated | Contact trust and safety team; migration is suspended during deletion review |
| ACC-5003 | No | Account has more than 50 billing contacts; the new platform allows a maximum of 50 | Remove or consolidate billing contacts, then retry |
| ACC-5004 | Yes | Account belongs to an organization whose primary account has not yet migrated | Wait for the primary account to migrate, then retry |
| ACC-5005 | No | Billing address contains unsupported characters (non-ASCII) | Update the billing address to use ASCII characters only |
| ACC-5006 | Yes | Account is under a legal hold; migration is blocked by the legal team | Contact your account manager; migration cannot proceed while the hold is active |
| ACC-5007 | No | Secondary email address on file is an alias that resolves to the same inbox as the primary | No action required; this is informational |
| ACC-5008 | Yes | Account merge was initiated but not completed; the account is in an intermediate state | Contact billing support to complete or cancel the account merge |
| ACC-5009 | No | Account creation date is in a format not recognized by the new platform (legacy format) | No action required; the date format is corrected automatically during migration |
| ACC-5010 | No | Phone number on account is in an invalid format for the new platform | Update the phone number in Account Settings > Contact Information |

## Data Integrity Error Codes (DAT-Series)

DAT-series errors occur when the migration engine detects inconsistencies
between the data it reads from the legacy platform and the data it writes to
the new platform. These errors indicate that the migration engine's
self-verification check failed.

| Error code | Blocking | Cause | Fix |
|---|---|---|---|
| DAT-6001 | Yes | Checksum mismatch: data written to new platform does not match data read from legacy | Retry migration; the migration engine will re-read and re-write the affected data |
| DAT-6002 | Yes | Record count mismatch: fewer records were written than were read | Retry migration; if the error persists, contact support with the DAT-6002 report |
| DAT-6003 | Yes | Duplicate record detected: the same record was written twice during migration | Contact billing support; do not retry until the duplicate is resolved |
| DAT-6004 | No | Orphan record detected: a child record references a parent that does not exist | Contact billing support to reconcile the orphan record |
| DAT-6005 | Yes | Referential integrity violation: a payment record references a deleted invoice | Contact billing support; this indicates legacy data corruption |
| DAT-6006 | No | Timestamp inconsistency: event timestamps are out of chronological order | No action required; timestamps are corrected automatically during migration |
| DAT-6007 | Yes | Encryption key mismatch: a record encrypted with a deprecated key cannot be decrypted | Contact billing support; this requires key rotation by the platform security team |
| DAT-6008 | No | Null field in a required column was filled with a default value during migration | Review the filled values in Billing > Settings and confirm they are correct |

## Network and Connectivity Error Codes (NET-Series)

NET-series errors are transient — they indicate that the migration engine
encountered a connectivity problem during data transfer. These errors
typically resolve automatically on retry. If a NET-series error persists after
three retries, escalate to billing support.

| Error code | Cause | Retry recommended |
|---|---|---|
| NET-7001 | Connection to legacy platform API timed out during read | Yes |
| NET-7002 | Connection to new platform API timed out during write | Yes |
| NET-7003 | DNS resolution failed for legacy platform API endpoint | Yes — if it persists, check platform status page |
| NET-7004 | SSL certificate validation failed for legacy platform endpoint | Yes — if it persists, contact support (may indicate a platform cert rotation) |
| NET-7005 | Rate limit exceeded on legacy platform read API | Yes — retry after 15 minutes |
| NET-7006 | Rate limit exceeded on new platform write API | Yes — retry after 15 minutes |
| NET-7007 | Migration engine node restarted mid-transfer (infrastructure event) | Yes — migration automatically resumes from last checkpoint |
| NET-7008 | Payload size exceeded maximum for a single transfer batch | No — contact support; large batch requires manual migration |

## Role and Permission Error Codes (ROLE-Series)

ROLE-series errors occur when billing roles or permissions cannot be migrated
because of configuration differences between the legacy and new platform.

| Error code | Blocking | Cause | Fix |
|---|---|---|---|
| ROLE-8001 | No | Custom billing role from legacy role builder cannot be mapped to a new platform role | Re-create the custom role in new platform Role Management within 30 days |
| ROLE-8002 | No | User assigned to a custom role has their role reset to Finance Viewer after migration | Reassign the correct role from Billing > Contacts > [User] > Edit Role |
| ROLE-8003 | Yes | Account Owner role is not assigned to any user on the account | Assign the Account Owner role to at least one user before retrying |
| ROLE-8004 | No | User with Billing Administrator role no longer exists in the identity system | Remove the non-existent user from the billing contact list |
| ROLE-8005 | No | Permission set from the legacy platform exceeds what the new platform's most privileged role allows | The user's permissions are capped at Billing Administrator level; contact support if higher access is needed |

## Platform Synchronization Error Codes (SYNC-Series)

SYNC-series errors indicate that the migration engine could not synchronize
data between the billing platform and an integrated system (identity provider,
accounting connector, ERP system).

| Error code | Blocking | Cause | Fix |
|---|---|---|---|
| SYNC-9001 | No | Accounting connector (QuickBooks, Xero, NetSuite) lost authentication during migration | Re-authenticate the accounting connector in Billing > Integrations |
| SYNC-9002 | No | CRM integration (Salesforce, HubSpot) could not sync updated account ID | Re-run the CRM sync manually from Billing > Integrations |
| SYNC-9003 | No | SCIM provisioner for the identity provider returned a conflict error | Contact your IT administrator to resolve the SCIM conflict |
| SYNC-9004 | No | ERP purchase order sync failed because the new platform's PO format changed | Update the ERP integration's PO format mapping and re-sync |
| SYNC-9005 | No | Tax platform integration (Avalara, TaxJar) API key is no longer valid | Re-enter the tax platform API key in Billing > Integrations > Tax |
| SYNC-9006 | No | Expense management integration could not map the new invoice line item format | Update the expense management integration and re-sync |
| SYNC-9007 | No | Slack or Teams billing notification bot lost its OAuth token during migration | Re-authorize the notification bot from Billing > Integrations |

---

## Error Code Ranges Reference

This table summarizes the ranges used across all error series to help you
quickly identify the category of an error code you are seeing.

| Range | Series | Category | Typical blocking behavior |
|---|---|---|---|
| ERR-4xxx | Core migration | Profile and data field errors | Blocking |
| ERR-5xxx | Core migration | Account state restrictions | Non-blocking (restricted state) |
| PAY-1xxx | Payment | Payment method errors | Blocking |
| INV-2xxx | Invoice | Invoice history and configuration | Mixed |
| TAX-3xxx | Tax | Tax identity and configuration | Mixed |
| SUB-4xxx | Subscription | Plan and entitlement mapping | Mixed |
| ACC-5xxx | Account | Profile and ownership | Mixed |
| DAT-6xxx | Data integrity | Checksum and record validation | Blocking |
| NET-7xxx | Network | Connectivity and timeouts | Non-blocking (transient) |
| ROLE-8xxx | Roles | Permission and role mapping | Non-blocking |
| SYNC-9xxx | Sync | Integration synchronization | Non-blocking |

---

## Escalation Decision Tree

Use this decision tree to determine whether to retry, self-resolve, or
escalate to billing support.

### Step 1: Identify the Series

Look at the prefix of your error code (ERR, PAY, INV, TAX, SUB, ACC, DAT,
NET, ROLE, SYNC) and refer to the series-specific table above.

### Step 2: Check if the Error Is Blocking

Blocking errors prevent migration from proceeding. Non-blocking errors allow
migration to complete but leave the account in a restricted state. The tables
above indicate whether each code is blocking.

### Step 3: Apply the Fix

Follow the fix instructions in the relevant table. Most fixes involve updating
or verifying a piece of account data and then retrying migration.

### Step 4: Retry

Retry migration from Billing > Overview > Resume Migration. You do not need
to re-read these instructions on each retry; the migration engine picks up
from the last successful checkpoint.

### Step 5: Escalate if the Error Recurs

If the same error code appears after two retry attempts:

1. Note the error code.
2. Note the account ID (visible in Account Settings > Account Information).
3. Note the time of the last retry (in your local timezone and UTC).
4. Open a support ticket from Help > Contact Support > Billing Migration Issue.
5. Include all three data points in the ticket.

Do not include payment card numbers, bank account numbers, or tax
identification numbers in your support ticket. The support team has secure
access to these records and does not need them in plain text.

---

## Diagnostic Commands for API Users

If you are integrating with the billing API and need to check migration status
or retrieve the current error code programmatically, use these endpoints.

### Check Migration Status

```
GET /v2/accounts/{account_id}/migration/status

Response:
{
  "migration_id": "mig_01HVXK3QZ...",
  "status": "queued" | "in_progress" | "completed" | "failed",
  "error_code": "ERR-4032" | null,
  "error_message": "...",
  "queued_at": "2026-06-01T08:00:00Z",
  "started_at": "2026-06-01T09:00:00Z" | null,
  "completed_at": null,
  "retry_count": 0
}
```

### Trigger a Retry

```
POST /v2/accounts/{account_id}/migration/retry

Response:
{
  "migration_id": "mig_01HVXK3QZ...",
  "status": "queued",
  "retry_count": 1
}
```

Retries are rate-limited to 1 per hour per account. If you attempt a retry
within the rate limit window, the API returns a `429 Too Many Requests`
response with a `Retry-After` header indicating the number of seconds until
the next retry is allowed.

### List All Error Codes for an Account

```
GET /v2/accounts/{account_id}/migration/errors

Response:
{
  "errors": [
    {
      "code": "ERR-4032",
      "series": "core",
      "blocking": true,
      "first_seen": "2026-06-01T09:12:34Z",
      "last_seen": "2026-06-01T09:12:34Z",
      "resolved": false
    }
  ]
}
```

---

## Error Code Change Log

The following error codes were added, removed, or changed in recent platform
updates.

| Version | Change | Error code | Description |
|---|---|---|---|
| 2026-05 | Added | PAY-1014 | 3DS re-authentication requirement for corporate cards |
| 2026-05 | Added | PAY-1015 | Minimum wallet balance requirement for transfer |
| 2026-04 | Modified | DAT-6007 | Expanded to cover all deprecated encryption keys (previously only covered AES-128) |
| 2026-04 | Added | SYNC-9007 | Slack and Teams bot OAuth token loss |
| 2026-03 | Deprecated | ERR-4020 | Replaced by PAY-1007; still returned by legacy migration engine for backward compatibility |
| 2026-03 | Added | ROLE-8005 | Permission cap behavior formalized as an explicit error |
| 2026-02 | Added | NET-7008 | Payload size limit error |
| 2026-01 | Added | TAX-3010 | Reverse-charge VAT configuration limitation |
| 2025-12 | Modified | INV-2003 | Changed from non-blocking to blocking; open overdue invoices now must be paid before migration |
| 2025-11 | Added | ACC-5008 | Account merge intermediate state |

---

## Frequently Asked Questions About Error Codes

**Can multiple error codes appear at the same time?**
Yes. A single migration attempt can surface multiple error codes if several
conditions are unmet simultaneously. All blocking errors must be resolved
before migration can proceed. You do not need to resolve non-blocking errors
before retrying — they will be re-evaluated as migration progresses.

**Will I lose data if migration fails?**
No. Migration is transactional. If a failure occurs during the in progress
phase, the migration engine rolls back any partial writes to the new platform.
The legacy platform remains unchanged and authoritative until migration
successfully completes.

**Is there an error code for "too many retries"?**
Not directly. However, if the migration engine detects that an account has
retried more than 5 times in a 24-hour window without a change in account
state, it enters a "manual review required" state. You will receive an email
and a support ticket is automatically opened on your behalf.

**My error code is not in this article. What should I do?**
Error codes not listed here are internal diagnostic codes generated by the
migration engine infrastructure. They are not intended to be acted on by
account administrators. Contact billing support with the exact error code,
and a support engineer will interpret the code and provide remediation
instructions.

**Can I prevent error codes from appearing?**
Most error codes can be avoided by completing the Pre-Migration Checklist in
the "Billing Profile Migration Overview" article before migration begins.
Completing the checklist resolves the conditions that cause the most common
blocking errors (ERR-4032, PAY-1001, PAY-1004, INV-2003, TAX-3002).

**How long do non-blocking error codes stay on my account?**
Non-blocking error codes remain visible on the migration status page until the
underlying condition is resolved. Once resolved, the error is marked as
"resolved" and archived in the migration event log. Archived errors remain
visible in the migration history for 12 months for audit purposes.
