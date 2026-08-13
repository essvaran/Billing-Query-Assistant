---
article_id: HC-BILL-001
product_area: billing-migration
last_updated: 2026-06-01
---

# Billing Profile Migration — Complete Implementation Guide

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

---

## Account Type Compatibility Matrix

Not all account types migrate in the same way. The table below describes how
the migration behaves for each account type and whether manual confirmation
is required.

| Account type | Auto-migrates | Confirmation required | Max migration window |
|---|---|---|---|
| Individual (personal) | Yes | No | 24 hours |
| Team (2–25 seats) | Yes | No | 24 hours |
| Business (26–500 seats) | Partial | Yes, by Account Owner | 48 hours |
| Enterprise (500+ seats) | No | Yes, by Account Owner + CS rep | 72 hours |
| Non-profit registered | Yes | No | 24 hours |
| Government contract | No | Scheduled by billing ops | Custom window |
| Reseller account | No | Coordinated with partner manager | Custom window |
| Trial (active) | Suspended until converted | N/A | N/A |
| Trial (expired) | Not migrated | N/A | N/A |

Enterprise and government accounts are migrated in scheduled windows to avoid
disruption. If your account falls into one of these categories, a member of
the billing operations team will contact you at least 14 days before your
scheduled window.

## Pre-Migration Checklist

Complete all items in this checklist before migration is initiated. Incomplete
items will not block migration from starting, but they will result in error
codes that pause migration mid-way and require manual intervention.

### Payment Method Verification

- [ ] At least one payment method is added and verified.
- [ ] If using a corporate card, the card's billing address matches the
      account's registered address.
- [ ] If using ACH/direct debit, a micro-deposit verification has been
      completed within the last 12 months.
- [ ] If using a purchase order, the PO number is valid and has not expired.
- [ ] The default payment method is explicitly set (do not rely on a single
      method being selected by default).

### Account and Contact Information

- [ ] The account owner email is active and accessible.
- [ ] Billing contacts have been reviewed and any outdated contacts removed.
- [ ] The registered business name matches the name on the primary payment
      method or bank account.
- [ ] The billing address is complete (street, city, state/province, postal
      code, country).

### Invoice and Tax Configuration

- [ ] Tax identification number (TIN/VAT/GST) is entered and validated.
- [ ] Tax exemption certificates, if applicable, are uploaded and approved.
- [ ] Custom invoice templates, if used, have been reviewed for compatibility.
      See the section "Custom Invoice Templates" below for the compatibility
      checklist.
- [ ] Invoice delivery method (email, postal, portal download) is confirmed.

### Dispute and Credit Resolution

- [ ] No open billing disputes exist on the account.
- [ ] Any pending credits have been applied or acknowledged.
- [ ] Any overpayments from the previous billing cycle have been reconciled.

### Subscription and Entitlement Review

- [ ] All active subscriptions are confirmed as intended (remove any accidental
      duplicates before migration).
- [ ] Any subscriptions on legacy pricing plans have been reviewed with a
      sales representative, as legacy plans may not carry over directly.
- [ ] Add-on services are confirmed as compatible with the new billing platform.
      See "Add-On Compatibility" in the Appendix.

---

## Migration Process — Phase by Phase

### Phase 1: Queued

When all prerequisites are met and the account is scheduled for migration, the
migration record enters **queued** status. During this phase:

- No billing data has been transferred yet.
- Normal billing operations continue on the legacy platform.
- You can continue adding, removing, or updating payment methods.
- Invoices generated during this phase are created on the legacy platform and
  will be migrated as historical records.

The queued phase typically lasts between 1 hour and 12 hours depending on
platform load. During peak migration windows (typically the first and last
business days of each month), queued status may persist for up to 24 hours.

### Phase 2: In Progress

When the migration engine picks up the account record, status changes to **in
progress**. This is an active state during which:

- Billing data is being read from the legacy platform and written to the new
  platform in a transactional sequence.
- Some operations are temporarily restricted to prevent data inconsistency.
  See the section "Operations Restricted During Migration" below.
- The Billing Overview page may show incomplete or stale data. This is
  expected. Do not interpret stale data as an error.
- Webhooks for billing events are paused. Events that occur during the in
  progress window will be replayed once the migration completes.
- API calls to the billing endpoints will receive a `503 Migration in Progress`
  response for write operations. Read operations remain available.

The in progress phase typically lasts 30 minutes to 4 hours. Accounts with
very large invoice histories (500+ invoices) may take up to 8 hours.

### Phase 3: Completed

When all billing data has been successfully transferred and verified, status
changes to **completed**. At this point:

- All billing operations resume on the new platform.
- Invoice numbering continues from the last legacy invoice number, incremented
  by 1. There is no gap in invoice numbers.
- Webhooks resume and any events queued during the in progress phase are
  replayed in chronological order within 15 minutes.
- API calls to billing endpoints return responses from the new platform.
- A migration summary email is sent to all billing contacts.

If the migration encounters an error during the in progress phase, status
reverts to **queued** with an error code attached. See the "Error Codes and
Fixes" article for a complete list of codes and their remediation steps.

---

## Operations Restricted During Migration

The following operations are not available while migration status is **in
progress**. Attempting these operations will return a `503 Migration in
Progress` error or a UI message asking you to try again later.

| Operation | Restriction level | Reason |
|---|---|---|
| Add a new payment method | Blocked | Prevents write conflicts on payment profile |
| Remove a payment method | Blocked | Prevents data loss during transfer |
| Change the default payment method | Blocked | Ensures consistent transfer of default flag |
| Generate a manual invoice | Blocked | Invoice numbering sequence must be locked |
| Apply a credit or coupon | Blocked | Credits are transferred as a batch; applying mid-transfer causes duplication |
| Change subscription plan | Blocked | Entitlement tables are locked during transfer |
| Cancel a subscription | Blocked | Cancellation records must be finalized after transfer |
| Update billing address | Blocked | Address data is part of the transferred profile |
| Download a new invoice | Available | Existing invoice data is read-only during transfer |
| View payment history | Available | Historical reads do not affect transfer integrity |
| Submit a support ticket | Available | Support access is never restricted |
| View subscription status | Available | Status reads are safe |

---

## Data Categories That Migrate

The following data is included in the migration and will be present in full on
the new billing platform after migration completes.

### Payment Methods

All payment methods are migrated, including:

- Credit and debit cards (Visa, Mastercard, Amex, Discover).
- ACH/direct debit bank accounts.
- Purchase orders with valid PO numbers.
- Pre-paid balances and wallet credits.
- Promotional credits applied before migration.

**Important:** Payment method tokens are re-tokenized during migration. If
your application stores the raw token returned by the legacy billing API, those
tokens will be invalidated. Retrieve new tokens from the new billing API after
migration completes. See the API migration guide for the token rotation
endpoint.

### Invoice History

All invoices are migrated. The original invoice number, date, line items,
tax amounts, applied discounts, and payment status are preserved exactly.
Invoices are migrated as read-only records; they cannot be edited after
migration because the legacy platform's approval audit trail is not migrated.

### Tax Information

Tax identification numbers (TIN, VAT, GST, ABN, and equivalent) are migrated.
If a tax exemption certificate was approved on the legacy platform and has not
expired, it is migrated with its original approval date and expiry.

### Subscription Entitlements

Active subscriptions and their associated seat counts, feature entitlements,
and renewal dates migrate exactly. The renewal date does not change as a
result of migration. Subscriptions that were canceled but still within a
paid period also migrate and retain their end date.

### Billing Contacts and Notification Preferences

All billing contact email addresses, their roles (primary, secondary,
read-only), and their notification preferences (invoice emails, payment
failure alerts, migration updates) migrate. If a billing contact email
address has bounced more than three times on the legacy platform, that contact
is marked inactive on the new platform and you will be asked to re-verify it.

---

## Data Categories That Do Not Migrate

The following data is not included in the migration. If you rely on any of
these, take manual action before or after the migration window.

| Data category | Action required |
|---|---|
| Custom invoice templates from the legacy template builder | Export from legacy settings and re-upload in new platform template manager |
| PDF invoice attachments stored in the legacy document vault | Download from legacy portal before migration; legacy portal remains accessible for 90 days post-migration |
| Legacy API keys scoped to billing endpoints | Generate new API keys from the new platform's developer settings |
| Saved payment method nicknames | Re-enter nicknames manually on the new platform |
| Internal billing notes added by support agents | These are retained by the support system, not migrated to billing profile |
| Scheduled future invoice drafts | Re-create in the new platform's invoice scheduler |
| Webhook endpoint configurations | Re-register webhooks using the new platform's webhook manager |

---

## Payment Method Handling During Migration

### What Happens to My Card Details?

Card details are never stored in plaintext on either platform. During
migration, the card network token is exchanged through a secure tokenization
gateway. The card number, expiry, and CVV are not transmitted between
platforms. Only the network token — a surrogate reference — is transferred.

If the token exchange fails for a specific payment method, that payment method
is marked as "needs re-verification" on the new platform. You will see a
banner prompting you to re-verify the card by completing a test transaction.
This does not mean your card details were lost; it means the token exchange
could not be confirmed.

### ACH and Bank Account Transfers

Bank account details for ACH payments are handled differently from card
payments. Because ACH does not use network tokens, the routing number and
last four digits of the account number are migrated as reference data. Before
the migrated ACH method can be used for a new transaction, you must complete
a one-time re-verification. A micro-deposit of less than $1.00 USD will be
sent to the bank account within 2 business days of migration completing.
Verify the amount in the Billing > Payment Methods section to activate the
method.

### Pre-Paid Balances

Any pre-paid balance on the legacy platform is transferred as a credit on the
new platform in the same currency. The credit appears on your next invoice as
"Migrated prepaid credit" and is applied before the payment method is charged.
If the credit exceeds the invoice total, the remaining credit carries forward
to the next billing cycle.

---

## Invoice History Migration and Numbering

### Invoice Number Continuity

Invoice numbers follow a continuous sequence. If your last legacy invoice was
INV-2024-08742, your first new-platform invoice will be INV-2024-08743. There
is no break in the sequence and no special prefix to indicate the platform
change.

### Accessing Legacy Invoices

After migration, legacy invoices are accessible in two ways:

1. **From the new platform:** The invoice list in Billing > Invoices shows all
   historical invoices, including pre-migration ones. Pre-migration invoices
   are labeled with a "Legacy" badge for the first 12 months.
2. **From the legacy portal:** The legacy portal remains available in read-only
   mode for 90 days after migration. You can download PDF copies of invoices
   during this window.

After 90 days, the legacy portal is decommissioned and legacy invoices are
only accessible through the new platform.

### Invoice Re-indexing for Large Accounts

Accounts with more than 50 invoices undergo invoice re-indexing during
migration. Re-indexing rebuilds the search index for all historical invoices
so that search and filter functions work correctly on the new platform. This
process runs in the background and extends the migration window by up to 48
hours for accounts with 500+ invoices. Invoices are accessible during
re-indexing; search results may be incomplete until re-indexing finishes.

---

## Tax Information Migration

### Supported Tax Identifier Types

| Tax ID type | Region | Migrates automatically | Manual re-entry needed |
|---|---|---|---|
| EIN (Employer Identification Number) | United States | Yes | No |
| SSN (used for sole traders) | United States | Yes | No |
| VAT number | European Union | Yes | No |
| GST number | Canada | Yes | No |
| GST/HST number | Canada | Yes | No |
| ABN (Australian Business Number) | Australia | Yes | No |
| GSTIN | India | Yes | No |
| RFC | Mexico | Yes | No |
| CNPJ | Brazil | Yes | No |
| Legacy custom tax ID | All regions | No | Yes |

Tax IDs stored in the "Legacy custom" field (used for tax jurisdictions that
were not natively supported before 2023) are not automatically migrated. If
your account uses a legacy custom tax ID, you will receive an email before
migration asking you to map it to a supported identifier type.

### Tax Exemption Certificates

Approved tax exemption certificates are migrated with their original approval
status. However, certificates that expire within 30 days of your migration
date are flagged for renewal. You will receive an email prompt to upload a
renewed certificate. Billing continues to apply the exemption until the
certificate expires; after expiry, standard tax rates apply until a renewed
certificate is approved.

---

## Subscription and Entitlement Migration

### Plan Mapping

Subscriptions on the new platform use updated plan IDs. The table below shows
the mapping from legacy plan IDs to new plan IDs. The features included in
each plan do not change; only the identifier changes in the API and on
invoices.

| Legacy plan ID | New plan ID | Display name | Seat range |
|---|---|---|---|
| PLAN-STARTER-V1 | PLAN-STARTER-2024 | Starter | 1–5 |
| PLAN-TEAM-V1 | PLAN-TEAM-2024 | Team | 6–25 |
| PLAN-TEAM-V2 | PLAN-TEAM-2024 | Team | 6–25 |
| PLAN-BUSINESS-V1 | PLAN-BUSINESS-2024 | Business | 26–200 |
| PLAN-BUSINESS-V2 | PLAN-BUSINESS-2024 | Business | 26–200 |
| PLAN-ENT-V1 | PLAN-ENTERPRISE-2024 | Enterprise | 201+ |
| PLAN-ENT-CUSTOM | PLAN-ENTERPRISE-CUSTOM | Enterprise Custom | Negotiated |
| PLAN-NFP-V1 | PLAN-NONPROFIT-2024 | Non-Profit | 1–500 |
| PLAN-GOV-V1 | PLAN-GOVERNMENT-2024 | Government | Negotiated |

If your legacy plan ID does not appear in this table, contact billing support
before your migration window. Unmapped plans are held in "plan review" status
and do not migrate until manually approved.

### Seat Count and Renewal Date Preservation

The seat count and subscription renewal date are preserved exactly during
migration. A subscription renewing on the 15th of each month will continue to
renew on the 15th after migration. A subscription with 47 seats will have 47
seats after migration. No re-purchase or re-configuration is required.

### Add-Ons and Feature Flags

Add-on services (advanced reporting, SSO, priority support, additional storage)
are migrated and remain active. Feature flags set by the account owner or a
support agent are migrated. Feature flags set by the billing operations team
for internal testing purposes are reset to defaults during migration.

---

## Multi-Account Organization Migration

If your account belongs to an organization with multiple child accounts, the
migration of each account is coordinated but sequential. The organization's
billing settings (consolidated invoicing, spending limits, approval workflows)
are migrated as a unit when the primary account (the account that pays the
consolidated invoice) completes migration.

### Migration Order Within an Organization

1. The primary (billing) account migrates first.
2. Child accounts are queued for migration in alphabetical order by account
   name.
3. Each child account migrates independently; a failure on one child does not
   block others.
4. Consolidated invoicing resumes once all child accounts have completed
   migration. During the period when some child accounts are migrated and some
   are not, invoices are generated separately per platform.

### Cross-Account Credits and Spending Limits

Cross-account credits (where a credit on the primary account is applied to
child account invoices) are suspended during the migration window. Any credit
that would have been applied during the suspension period is added as a
carryover credit on the primary account's next invoice.

Spending limits set at the organization level are preserved. Spending limits
set at the individual child account level may need to be re-confirmed after
migration because they are validated against the new platform's entitlement
service.

---

## Single Sign-On and Identity Impact

Billing migration does not affect your SSO configuration. The identity provider
(IdP) connection, attribute mapping, and SCIM provisioning settings live in
a separate identity management system that is not part of the billing platform.
However, if your SSO setup includes role-based billing access (for example,
members of an "FinanceTeam" group automatically receive the Finance Viewer
billing role), those role assignments are preserved because billing roles are
stored against the user record in the identity system, not in the billing
profile.

The one exception is custom billing roles created using the legacy role
builder. These custom roles are not migrated automatically. See the "Role
and Permission Migration" section of this article.

---

## API and Webhook Changes After Migration

### Endpoint Changes

The new billing platform exposes a different API base URL. After migration,
update your integrations to use the new base URL. Both URLs remain active for
a 90-day transition period, after which the legacy endpoint is retired.

| Environment | Legacy base URL | New base URL |
|---|---|---|
| Production | api.billing-legacy.example.com/v1 | api.billing.example.com/v2 |
| Staging | api.billing-legacy-staging.example.com/v1 | api.billing-staging.example.com/v2 |
| Sandbox | api.billing-sandbox-legacy.example.com/v1 | api.billing-sandbox.example.com/v2 |

### Breaking Changes in the New API

| Legacy endpoint | Change type | New behavior |
|---|---|---|
| GET /invoices | Response schema updated | `invoice_number` field renamed to `number`; `created_at` now ISO 8601 with timezone |
| POST /payment-methods | Tokenization changed | Returns `token_v2` instead of `token`; `token` field included for 90-day backward compatibility |
| GET /subscriptions | Plan ID format changed | Returns new plan IDs; legacy plan IDs available in `legacy_plan_id` field for 90 days |
| POST /credits | New required field | Requires `reason_code` field; accepted values: ADJUSTMENT, REFUND, PROMOTIONAL |
| DELETE /payment-methods/:id | Behavior change | Returns 409 if method is the only verified payment method (legacy returned 200 and silently failed) |

### Webhook Event Changes

Webhooks are paused during the in progress phase and replayed after migration
completes. The replay order is chronological by event timestamp. If your
webhook handler is not idempotent, duplicate events may cause issues because
the replay can re-fire events that were successfully delivered before migration
began. Review your webhook handler's idempotency before the migration window.

New events available on the new platform that do not exist on the legacy
platform:

| Event name | Fired when |
|---|---|
| billing.migration.completed | Account migration finishes successfully |
| billing.migration.failed | Migration encountered an unrecoverable error |
| billing.token.rotated | A payment method token was re-tokenized during migration |
| billing.credit.migrated | A pre-paid balance was transferred as a migrated credit |

---

## Custom Invoice Templates

Custom invoice templates from the legacy template builder are not
automatically migrated. The new platform uses a different template engine
(Liquid-based) that is not backward compatible with the legacy engine
(Mustache-based).

### Compatibility Checklist for Custom Templates

Before migration, review your custom template against this compatibility list:

| Legacy template feature | Compatible with new platform | Action |
|---|---|---|
| Company logo (PNG/SVG) | Yes | Automatically available |
| Custom header text | Yes | Carried over from legacy |
| Custom footer text | Yes | Carried over from legacy |
| Mustache-style variable substitution (`{{variable}}`) | No | Must rewrite in Liquid syntax (`{{ variable }}`) |
| Conditional blocks (`{{#if}}`) | No | Must rewrite as Liquid conditionals (`{% if %}`) |
| Custom CSS in template | Partially | Inline styles only; external stylesheets not supported |
| Multi-language templates | Yes | Language selection logic must be rewritten in Liquid |
| QR code in footer | No | QR code generation is a new platform feature configured separately |

### Re-creating a Template After Migration

After migration completes, go to Billing > Settings > Invoice Templates. The
new template editor provides:

- A WYSIWYG editor for non-technical users.
- A raw Liquid template editor for developers.
- A library of 12 pre-built templates that match common layouts.
- A template import tool that attempts to convert Mustache syntax to Liquid.
  The import conversion is best-effort and may require manual correction.

---

## Billing Contacts and Notification Settings

### Contact Roles

Each billing contact on the account can be assigned one of the following
roles. Roles control what actions a contact can take and which notifications
they receive.

| Role | Can view invoices | Can pay invoices | Can change payment methods | Can change billing settings | Receives all billing emails |
|---|---|---|---|---|---|
| Account Owner | Yes | Yes | Yes | Yes | Yes |
| Billing Administrator | Yes | Yes | Yes | Yes | Yes |
| Finance Viewer | Yes | No | No | No | Invoice emails only |
| Payment Approver | Yes | Yes | No | No | Payment-related only |
| Auditor (read-only) | Yes | No | No | No | No |

### Notification Categories

| Category | Default state | How to adjust |
|---|---|---|
| Invoice generated | On | Billing > Notifications |
| Payment successful | On | Billing > Notifications |
| Payment failed | On, cannot be turned off for Account Owner | Billing > Notifications |
| Migration status updates | On during migration window, auto-disabled after | Billing > Notifications |
| Subscription renewal reminder | On (14 days before) | Billing > Notifications |
| Spending limit alert | Off by default | Billing > Spending Limits |
| Dispute opened/resolved | On | Billing > Notifications |

---

## Credit Balance Handling

### Types of Credits

The new billing platform distinguishes between four types of credit:

| Credit type | Source | Expiry | Refundable |
|---|---|---|---|
| Promotional | Issued by sales or marketing | As specified (usually 90 days) | No |
| Adjustment | Issued by support for billing errors | 12 months | No |
| Migrated prepaid | Transferred pre-paid balance from legacy | None | On request |
| Refund credit | Issued instead of a payment reversal | 24 months | Yes, if unused |

### Credit Application Order

When an invoice is generated, credits are applied in this order:

1. Refund credits (oldest first).
2. Migrated prepaid credits.
3. Adjustment credits (oldest first).
4. Promotional credits (earliest expiry first).

This order ensures that credits with the earliest expiry are used first to
prevent unexpected expiration.

---

## Recurring Billing and Auto-Pay Impact

Auto-pay is paused automatically during migration and does not resume until
the account owner confirms the new default payment method. If a billing cycle
falls during the migration window, the invoice is generated but payment is
deferred. Once migration completes and auto-pay resumes, any deferred
invoices are paid immediately using the default payment method. If the
deferred period spans more than one billing cycle, each deferred invoice is
paid separately in chronological order.

A grace period of 7 days applies during the migration window. Late payment
fees are not charged for invoices that become due during the in progress phase,
provided payment is made within 7 days of migration completing.

---

## Trial and Promotional Pricing Impact

### Active Trial Accounts

Trial accounts cannot be migrated until the trial is converted to a paid
subscription. Migration for a trial account is queued but will not proceed to
in progress until the trial conversion is complete.

### Promotional Pricing

If an account has a promotional price applied to a subscription (for example,
a 20% discount for the first 12 months), that promotional price is preserved
through migration. The promotional period does not reset; if 4 months of a
12-month promotion have elapsed, 8 months remain after migration.

### Legacy Grandfathered Pricing

Accounts on grandfathered legacy pricing plans (plans that were discontinued
after 2022 but kept for existing subscribers) will see their pricing preserved
through migration. The plan features will be mapped to the equivalent new
platform entitlements. If a grandfathered plan has no direct equivalent on the
new platform, a billing operations specialist will contact the account owner to
discuss options at least 30 days before the migration window.

---

## Migration Status Notifications

### Email Notifications Sent Automatically

| Notification | Sent when | Recipients |
|---|---|---|
| Migration scheduled | 7 days before window | Account Owner, Billing Administrator |
| Migration starting | 1 hour before in progress | Account Owner, Billing Administrator |
| Migration completed | Immediately after completion | All billing contacts |
| Migration failed | Immediately after failure | Account Owner, Billing Administrator |
| Action required | When a blocking condition is detected | Account Owner |
| Re-verification required | When a payment method needs re-verification | Account Owner, Billing Administrator |

### In-App Banners

During the migration window, banners appear in the Billing Overview page:

- **Blue banner:** Migration is queued or in progress.
- **Green banner:** Migration completed successfully.
- **Red banner:** Migration failed. Includes the error code and a link to the
  remediation article.
- **Yellow banner:** Action required to unblock migration.

---

## Audit Log and Compliance Records

All migration events are written to the account's audit log with a
`billing.migration.*` event type. The audit log is available under
Account Settings > Audit Log. Audit log records cannot be deleted and are
retained for 7 years in accordance with financial record-keeping requirements.

### Audit Log Event Types for Migration

| Event type | Description |
|---|---|
| billing.migration.scheduled | Migration window assigned to account |
| billing.migration.prerequisites_check | Automated prerequisite validation run |
| billing.migration.started | In progress phase began |
| billing.migration.data_transfer_completed | All data successfully copied to new platform |
| billing.migration.verification_passed | Post-transfer data integrity check passed |
| billing.migration.completed | Migration finalized; account now on new platform |
| billing.migration.failed | Error encountered; status reverted to queued |
| billing.migration.rollback_requested | Rollback request submitted |
| billing.migration.rollback_completed | Rollback to legacy platform completed |

---

## Post-Migration Verification Checklist

After migration completes, verify the following before treating migration as
done:

### Immediate Checks (within 1 hour)

- [ ] Invoice list shows all historical invoices, including pre-migration ones.
- [ ] The default payment method is correct.
- [ ] Subscription plan and seat count are correct.
- [ ] Billing contacts are all present and have correct roles.
- [ ] Tax ID is displayed correctly.
- [ ] Outstanding invoice balance (if any) matches expectations.

### Next Billing Cycle

- [ ] Auto-pay successfully charged the default payment method.
- [ ] Invoice generated with the correct subscription line items.
- [ ] Invoice number follows the expected sequence.
- [ ] Tax was calculated correctly.
- [ ] Any promotional or adjustment credits were applied in the correct order.

### API and Integrations (within 24 hours)

- [ ] API integration updated to use new base URL.
- [ ] New payment method tokens retrieved and stored.
- [ ] Webhook endpoint re-registered if not done before migration.
- [ ] Webhook handler confirmed receiving migration replay events.
- [ ] Reporting integration pulling data from new platform.

---

## Known Limitations of This Migration

The following limitations apply to this migration. Where a workaround exists,
it is noted.

| Limitation | Impact | Workaround |
|---|---|---|
| Legacy custom tax IDs not migrated automatically | Tax may be calculated without exemption if not remediated | Map to a supported tax ID type before migration |
| Custom invoice templates require rewrite | Invoices revert to default template until new template is created | Create new template using provided Liquid template library |
| Payment method nicknames not migrated | Users must re-add nicknames | Use Bulk Nickname Import tool in Payment Methods settings |
| Webhook endpoints not migrated | Webhooks silently dropped until re-registered | Re-register before migration using new platform's webhook manager |
| Legacy API keys invalidated | Integrations break immediately on migration completion | Generate new keys from Developer Settings before migration |
| Invoice draft scheduler reset | Any drafts created in the legacy scheduler are lost | Export draft list from legacy and re-create in new scheduler |
| Custom roles from legacy role builder not migrated | Users with custom roles revert to Finance Viewer | Re-create roles in new Role Management settings within 30 days |

---

## Frequently Asked Questions

**Will migration affect my current subscription or pricing?**
No. Subscription terms, pricing, seat counts, and renewal dates are preserved
exactly. Migration is a platform transfer, not a contract change.

**Do I need to re-enter my payment information?**
Most payment methods are migrated automatically. You may be asked to re-verify
a payment method if the token exchange cannot be confirmed during migration. A
re-verification prompt will appear on the Billing Overview page.

**Will my invoice number reset after migration?**
No. Invoice numbers continue from where the legacy platform left off. If your
last legacy invoice was INV-2024-08742, your next invoice will be
INV-2024-08743.

**What happens if I receive an invoice during the migration window?**
Invoices generated during the in progress phase are deferred. Payment is
collected automatically within 24 hours of migration completing. A 7-day
grace period applies; late fees are not charged during this window.

**Can I opt out of migration?**
No. Migration to the new billing platform is mandatory for all accounts.
However, the timing of your migration window can be adjusted in limited
circumstances. Contact billing support at least 14 days before your scheduled
window to request a reschedule.

**What happens to my tax exemption certificates?**
Approved certificates are migrated. If a certificate expires within 30 days
of your migration date, you will receive a renewal prompt. Billing continues
to apply the exemption until the certificate expires.

**How do I know when migration is complete?**
You will receive an email to all billing contacts when migration completes. A
green confirmation banner also appears on the Billing Overview page.

**Can migration be reversed after it completes?**
No. Once migration reaches completed status, it cannot be rolled back.
Invoice numbering and tax records have already switched to the new platform's
format, and reversing them would create compliance issues.

**Why does my Billing Overview page show incomplete data during migration?**
The Billing Overview page reads from the new platform as soon as migration
starts. While data is still being transferred, some fields may show as empty
or stale. This is expected. The page returns to normal once migration completes.

**Are there any downtime windows during migration?**
No planned downtime. Write operations to billing endpoints are blocked during
the in progress phase (returning 503 responses), but the platform remains
accessible and all read operations are available.

**What if I update my payment method right before migration starts?**
Updates made less than 1 hour before the in progress phase may not be captured
before the profile snapshot is taken. If you need to update a payment method,
do so at least 2 hours before your scheduled migration window.

**How do multi-account organizations handle a failure in one child account?**
A failure in one child account does not block other child accounts or the
primary account from completing migration. The failed child account retries
independently once the error is resolved.

**Will my API keys stop working immediately after migration?**
Legacy API keys continue to work against the legacy API endpoint for 90 days
after migration. After 90 days, the legacy endpoint is retired and only new
API keys on the new endpoint will work.

**Can I generate a new invoice manually during migration?**
No. Manual invoice generation is blocked during the in progress phase. Once
migration completes, you can generate invoices normally.

**Does migration affect my SSO login?**
No. SSO configuration is managed by the identity platform, which is separate
from billing. Login is not affected.

**What is the difference between a queued and a stuck migration?**
Queued is the normal waiting state before migration begins. Stuck is an
informal term for a migration that has been in queued status for longer than
expected — usually because a prerequisite is not met. If your migration has
been queued for more than 24 hours, check the Billing Overview page for a
yellow "Action required" banner.

**Do I need to do anything for my recurring billing after migration?**
Auto-pay resumes automatically after migration. No action is required unless
the account owner is prompted to confirm the default payment method.

**Will I lose my promotional discount after migration?**
No. Promotional pricing, including grandfathered legacy pricing, is preserved
through migration.

**How are invoice PDFs handled after the legacy portal is decommissioned?**
All invoice PDFs, including those generated on the legacy platform, are
accessible from the new platform's invoice list. The legacy portal remains
available for 90 days as a backup access method.

**What should I do if I see a billing discrepancy after migration?**
Submit a billing dispute from Billing > Invoices > [Invoice] > Dispute. Include
the invoice number and a description of the discrepancy. The billing support
team will investigate and respond within 5 business days.

---

## Glossary

**Account Owner:** The user with the highest privilege level on a billing
account. Responsible for confirming migration and is the primary recipient of
billing notifications.

**ACH:** Automated Clearing House. A US-based electronic bank transfer network
used for direct debit payment methods.

**Billing Administrator:** A secondary role with full billing access. Can
perform all billing operations except modify the Account Owner role.

**Billing Contact:** Any user with a billing role on the account who receives
billing notifications.

**Chargeback:** A payment reversal initiated by the card issuer at the
cardholder's request. Opens a dispute on the billing account.

**Credit:** A positive balance applied to an account that reduces the amount
charged on the next invoice.

**Entitlement:** A feature or resource limit granted by a subscription plan.

**Finance Viewer:** A read-only billing role. Can view invoices and payment
history but cannot make changes.

**Grandfathered Plan:** A subscription plan that is no longer offered to new
customers but is retained for existing subscribers who subscribed before the
plan was discontinued.

**Invoice:** A document requesting payment for services rendered, generated
at the end of each billing cycle.

**Legacy Platform:** The previous billing infrastructure that accounts are
migrating away from.

**Migration Window:** The scheduled time period during which an account's
billing data is transferred from the legacy platform to the new platform.

**New Platform:** The current billing infrastructure that all accounts are
migrating to.

**Plan ID:** A unique identifier for a subscription plan. Changes from legacy
format to new format during migration.

**PO (Purchase Order):** A payment method used by businesses to pay invoices
against an approved purchase order number.

**SSO (Single Sign-On):** A method of authentication that allows users to
log in with a single set of credentials managed by an external identity
provider.

**Token:** A surrogate reference that represents a payment method without
storing the actual card or bank details.

**TIN (Tax Identification Number):** A number assigned by a tax authority to
identify a taxpayer.

**Webhook:** An HTTP callback sent from the billing platform to a registered
endpoint when a billing event occurs.

---

## Appendix A: Platform Comparison

| Feature | Legacy platform | New platform |
|---|---|---|
| API version | v1 | v2 |
| Webhook delivery guarantee | At least once | Exactly once (with idempotency key) |
| Invoice template engine | Mustache | Liquid |
| Token format | 32-char alphanumeric | UUID v4 |
| Tax engine | Rule-based (manual maintenance) | API-driven (auto-updated for new jurisdictions) |
| Audit log retention | 3 years | 7 years |
| Credit types | 2 (promotional, adjustment) | 4 (promotional, adjustment, migrated prepaid, refund) |
| SSO integration | SAML 2.0 only | SAML 2.0 + OIDC |
| Spending limits | Account-level only | Account-level and organization-level |
| Multi-currency invoicing | USD only | 25+ currencies |
| Invoice PDF generation | Synchronous | Asynchronous (webhook notification on ready) |
| Sandbox environment | Shared | Dedicated per account |

## Appendix B: Migration Timeline by Account Size

| Account size (invoices) | Queued phase | In progress phase | Total max window |
|---|---|---|---|
| 0–10 invoices | 1–6 hours | 30 minutes | 7 hours |
| 11–50 invoices | 1–12 hours | 30–60 minutes | 13 hours |
| 51–200 invoices | 1–12 hours | 1–4 hours | 16 hours |
| 201–500 invoices | 1–24 hours | 4–8 hours | 32 hours |
| 501–2000 invoices | 12–24 hours | 8–24 hours | 48 hours |
| 2001+ invoices | Scheduled window | 24–72 hours | Coordinated with billing ops |

---

## Troubleshooting Guide — Migration Phase by Phase

This section walks through the most common problems encountered at each phase
of migration and provides step-by-step resolution instructions.

### Troubleshooting: Migration Stuck in Queued Status

A migration that has been in queued status for more than 24 hours is considered
stuck. The most common causes and resolutions are described below.

**Cause 1: Unresolved prerequisite**

Check the Billing Overview page for a yellow "Action required" banner. The
banner will state which prerequisite is unresolved. Common unresolved
prerequisites include an expired payment method, an open billing dispute, or
an unsigned updated billing terms agreement.

Resolution steps:
1. Navigate to Billing > Overview.
2. Read the "Action required" banner carefully.
3. Follow the link in the banner to the affected section.
4. Complete the required action.
5. Return to Billing > Overview and click "Resume migration."

**Cause 2: Prerequisite check ran before the action was saved**

If you completed an action (for example, added a new payment method) but
migration is still showing as stuck, the prerequisite check may have run
before your change was saved to the database. The check runs every 4 hours.

Resolution steps:
1. Confirm the action was saved by navigating to the relevant settings page
   and verifying the change appears.
2. Wait up to 4 hours for the next automatic prerequisite check.
3. Alternatively, trigger a manual prerequisite check from Billing > Overview
   by clicking "Check prerequisites now."

**Cause 3: Account belongs to an organization whose primary account is stuck**

If your account is a child account in a multi-account organization, migration
of child accounts is blocked until the primary account completes migration.

Resolution steps:
1. Identify the primary account for your organization from Account Settings >
   Organization.
2. Contact the account owner of the primary account and ask them to check their
   migration status.
3. Once the primary account completes migration, your account's migration will
   resume automatically within 2 hours.

**Cause 4: Platform migration queue is at capacity**

During peak migration periods (first and last business days of each month),
the migration queue may be at capacity. Accounts are processed in the order
they entered the queue.

Resolution steps:
1. Check the platform status page for any posted migration queue delays.
2. No action required; migration will proceed automatically as capacity
   becomes available.

---

### Troubleshooting: Migration Failed During In Progress Phase

If migration fails during the in progress phase, the status reverts to queued
and an error code is attached. The migration engine has already rolled back
any partial writes to the new platform — no data has been lost.

**General resolution steps:**

1. Note the error code displayed on the Billing Overview page.
2. Look up the error code in the "Billing Migration Error Codes and Fixes"
   article.
3. Apply the fix described for that error code.
4. Return to Billing > Overview and click "Resume migration."
5. Monitor the migration status for 30–60 minutes to confirm it transitions
   to "in progress" and then to "completed."

**If the error code is not in the article:**

Internal diagnostic codes (not documented in the error code article) indicate
infrastructure-level problems that cannot be resolved by account
administrators. Submit a support ticket from Help > Contact Support >
Billing Migration Issue. The support team will investigate and respond
within 4 business hours.

**If migration fails on the same step three times in a row:**

This indicates a persistent data problem that retries will not fix. Stop
retrying and escalate immediately. Continued retries on a persistently failing
migration can complicate the support team's ability to diagnose the issue
because each retry generates a new event log entry.

---

### Troubleshooting: Billing Overview Shows Incorrect Data After Migration

If the Billing Overview page shows incorrect or stale data after migration
completes (for example, wrong subscription plan, missing invoices, or a zero
balance when a credit is expected), follow these steps:

1. **Clear your browser cache.** The Billing Overview page caches some data
   client-side for performance. A hard refresh (Ctrl+Shift+R or Cmd+Shift+R)
   forces the page to re-fetch from the server.

2. **Wait 15 minutes.** Some data (particularly migrated pre-paid credits and
   subscription entitlements) is written asynchronously after the main
   migration completes. The Billing Overview page may not reflect these items
   immediately.

3. **Check the migration completion email.** The email sent to billing contacts
   on migration completion includes a summary of what was migrated. If the
   email summary matches the page, the data is correct and the display issue
   is a browser cache problem.

4. **Check the audit log.** Navigate to Account Settings > Audit Log and
   filter by "billing.migration.*" events. The log will show exactly what
   data was transferred and when.

5. **Submit a support ticket if the issue persists.** If the page is still
   showing incorrect data 2 hours after migration completed, submit a support
   ticket. Include a screenshot of the incorrect data and the migration ID
   from the audit log.

---

### Troubleshooting: Payment Method Marked as Needs Re-Verification After Migration

If one or more payment methods are marked as "Needs re-verification" after
migration, this means the token exchange for that payment method could not be
confirmed during migration. The payment method is retained on the account but
is not active until re-verification is complete.

**For credit and debit cards:**

1. Navigate to Billing > Payment Methods.
2. Find the card marked as "Needs re-verification."
3. Click "Verify now."
4. Complete the verification by entering the card's CVV. A test authorization
   of $0.00 to $1.00 is placed and immediately released.
5. If the verification succeeds, the card becomes the active payment method.
6. If the verification fails, the card issuer has declined the verification.
   Add a new card or use an alternative payment method.

**For ACH bank accounts:**

1. Navigate to Billing > Payment Methods.
2. Find the bank account marked as "Needs re-verification."
3. Click "Verify with micro-deposit."
4. A micro-deposit of two amounts, each less than $1.00 USD, will be sent
   to the bank account within 2 business days.
5. Once the deposits appear on your bank statement, enter the amounts in
   Billing > Payment Methods > [Bank Account] > Enter deposit amounts.
6. If the amounts match, the bank account is verified and active.

---

### Troubleshooting: Webhooks Not Firing After Migration

If your webhook endpoints are not receiving events after migration completes,
the most likely causes are:

**Cause 1: Webhook endpoints were not re-registered on the new platform**

Webhook configurations are not migrated automatically. You must re-register
your webhook endpoints on the new platform.

Resolution:
1. Navigate to Developer Settings > Webhooks.
2. Click "Add endpoint."
3. Enter the endpoint URL and select the event types you want to receive.
4. Save the endpoint.
5. Test the endpoint by clicking "Send test event."

**Cause 2: Replayed events from migration were rejected by your handler**

During migration, the new platform replays any billing events that occurred
while webhooks were paused. If your handler rejected these replayed events
(for example, because they appeared to be duplicates), you may be missing
updates.

Resolution:
1. Review the webhook delivery log in Developer Settings > Webhooks > [Endpoint]
   > Delivery log.
2. For any events showing a non-2xx response, re-process them manually or
   trigger a re-delivery from the delivery log.
3. Update your webhook handler to be idempotent. Check the `idempotency_key`
   field in the event payload and skip processing if you have already handled
   that key.

**Cause 3: Event types changed on the new platform**

Some event types have been renamed or replaced on the new platform. If you
are subscribing to a deprecated event type, you will not receive events.

Resolution:
1. Review the webhook event change log in the API changelog.
2. Update your subscription to use the new event type names.

---

## Regional Compliance and Data Residency

### Data Residency Options

Billing data is stored in the region closest to your account's registered
address by default. Enterprise and Government accounts can request a specific
data residency region.

| Region | Data center locations | Available to |
|---|---|---|
| United States | Virginia, Oregon | All account types |
| European Union | Frankfurt, Amsterdam | All account types |
| United Kingdom | London | All account types |
| Australia | Sydney | All account types |
| Canada | Toronto, Montreal | All account types |
| Japan | Tokyo | Enterprise and Government only |
| Singapore | Singapore | Enterprise and Government only |
| Brazil | São Paulo | Enterprise and Government only |

Data residency selection is made during account creation or can be requested
by submitting a Data Residency Change Request through billing support. Changes
to data residency require a full re-migration of billing data and are typically
completed within 14 business days.

### Compliance Certifications

The new billing platform has been certified for the following compliance
frameworks:

| Framework | Scope | Certificate available |
|---|---|---|
| SOC 2 Type II | Security, availability, confidentiality | Yes, on request |
| ISO 27001 | Information security management | Yes, on request |
| PCI DSS Level 1 | Payment card data handling | Yes, on request |
| GDPR | EU personal data processing | Data Processing Agreement available |
| HIPAA | Health information (if applicable) | BAA available for qualifying accounts |
| FedRAMP Moderate | US government cloud services | In progress (expected Q4 2026) |
| CCPA | California consumer privacy | Privacy Notice available |

### GDPR-Specific Behavior During Migration

During migration, billing data for EU accounts is processed within the EU
data center and is not transferred to non-EU data centers at any point. The
migration engine that processes EU accounts runs entirely within the EU region.

If you require a Data Processing Agreement (DPA) for the migration, contact
your account manager before the migration window. A DPA can be signed and
attached to your account before migration begins.

### Right to Erasure and Migration

The right to erasure (GDPR Article 17) does not apply to billing records
because they are required for tax and financial compliance purposes under
GDPR Article 17(3)(b). Billing records are retained for 7 years after the
end of the relevant tax year.

---

## Security During Migration

### Encryption in Transit

All data transferred between the legacy platform and the new platform during
migration is encrypted using TLS 1.3. The migration engine does not decrypt
and re-encrypt data at rest — it transfers data between encrypted storage
layers using a secure key exchange protocol managed by the platform security
team.

### Encryption at Rest

Billing data on both platforms is encrypted at rest using AES-256. Payment
method tokens are encrypted using the card network's encryption keys and are
never stored in plaintext on either platform.

### Access Control During Migration

During the in progress phase, write access to billing data is restricted to
the migration engine service account. Human administrators — including billing
support agents and platform engineers — do not have direct write access to
billing data during the migration. All reads by support agents are logged.

### Security Event Logging During Migration

In addition to the billing audit log, all access to billing data during
migration is logged in the platform security event log. Security event logs
are separate from the billing audit log and are available to the account
owner on request by submitting a Security Log Access Request through support.

---

## Change Management Recommendations

For organizations with multiple stakeholders affected by billing migration,
the following change management steps are recommended to minimize disruption.

### 14 Days Before Migration

| Task | Owner | Notes |
|---|---|---|
| Communicate migration date to finance team | Account Owner | Include expected window and any disruptions |
| Review API integrations for breaking changes | Engineering lead | See API Changes section |
| Re-register webhook endpoints on new platform | Engineering lead | Can be done before migration; events will not fire until migration completes |
| Complete the Pre-Migration Checklist | Billing Administrator | Available in the main migration guide |
| Brief accounts payable team | Finance lead | Explain invoice deferral during migration window |

### 7 Days Before Migration

| Task | Owner | Notes |
|---|---|---|
| Generate new API keys on new platform | Engineering lead | Legacy keys still work for 90 days; start transitioning now |
| Update integration configurations to use new base URL | Engineering lead | Use dual-write for 90 days if needed |
| Confirm all billing contacts have valid email addresses | Billing Administrator | Bounced contacts will not receive migration notifications |
| Download any invoice PDFs needed immediately | Finance lead | Legacy portal decommissioned 90 days post-migration |
| Brief customer success team | Account Owner | Inform them of any expected billing disruptions during window |

### Day of Migration

| Task | Owner | Notes |
|---|---|---|
| Monitor migration status | Billing Administrator | Check Billing Overview every hour during in progress phase |
| Pause any scheduled billing-related batch jobs | Engineering lead | Batch jobs calling the billing API will receive 503 responses |
| Notify finance team when in progress phase begins | Account Owner | A brief heads-up prevents confusion if reports show stale data |

### After Migration Completes

| Task | Owner | Notes |
|---|---|---|
| Complete Post-Migration Verification Checklist | Billing Administrator | See the checklist section in this article |
| Test a billing API call on the new base URL | Engineering lead | Confirm the integration is routing to the new platform |
| Confirm webhook events are flowing | Engineering lead | Check delivery log in Developer Settings |
| Notify finance team that billing is restored | Account Owner | |
| Re-create custom invoice templates if needed | Finance lead | See Custom Invoice Templates section |
| Re-enter payment method nicknames | Billing Administrator | Nicknames are not migrated |

---

## Extended FAQ — Additional Questions

**What if I miss my migration window?**
If you do not complete any required actions before your migration window, the
window is extended automatically. Migration will not proceed to the in
progress phase until all blocking prerequisites are met. There is no penalty
for missing the original window.

**Can I have two active subscriptions after migration?**
Yes. Migration does not change the number of active subscriptions on the
account. If you had two active subscriptions before migration, you will have
two after.

**What happens to my billing address if I have multiple addresses on file?**
The default billing address is migrated and remains the default. All
additional addresses are also migrated. The default address selection does not
change.

**How are refunds handled during migration?**
Pending refunds initiated before migration are processed on the legacy platform
before the migration window begins. Refunds requested during the migration
window are queued and processed on the new platform after migration completes.

**Is there a way to test migration in a staging environment?**
Yes. If your account has a linked staging or sandbox environment, a test
migration is automatically run against the staging environment 48 hours before
the production migration window. The test migration uses production data
snapshots to validate the migration process. Results of the test migration are
emailed to billing contacts.

**Will my usage data and analytics reset after migration?**
No. Usage data and analytics are stored in a separate analytics system that
is not part of the billing profile migration. Your usage history is unaffected.

**Can I change the account owner before migration?**
Yes, but it is strongly recommended to complete the account owner change at
least 72 hours before the migration window to ensure the new owner's email
is verified and the change is reflected in the billing profile before migration
is scheduled.

**What if I discover a discrepancy in my invoice history after migration?**
Submit a billing dispute from Billing > Invoices > [Invoice] > Dispute. The
billing support team will compare the new platform's records with the legacy
platform's records (the legacy platform remains in read-only mode for 90 days
after migration) and resolve any discrepancy.

**Do I need to update my accounts payable system after migration?**
If your accounts payable system stores the billing platform's API base URL
or invoice portal URL, update these references after migration. Invoice
numbers and amounts will not change, so existing records in your AP system
remain accurate.

**What is the migration engine?**
The migration engine is the internal service that reads billing data from the
legacy platform and writes it to the new platform. It runs as a managed
service inside the billing platform infrastructure and is not directly
accessible to account administrators or support agents.

**How many accounts are migrated simultaneously?**
The migration engine runs up to 500 accounts in parallel during a migration
window. Accounts are batched by size to prevent large accounts from blocking
the queue. Enterprise and Government accounts are migrated in dedicated batches
outside of the shared migration window.

**Can I pause migration once it has started?**
Migration cannot be paused once the in progress phase has begun. If you need
to stop migration, wait until it either completes or fails. If it fails, it
automatically reverts to queued status and no further action is taken until
you retry.

**What if my company name changes during the migration window?**
If your registered business name changes during the migration window, wait
until migration completes before updating the name. Updating account details
during the in progress phase may cause a data consistency error.

**Are there any file size limits on tax exemption certificates?**
Yes. The new platform accepts PDF files up to 10 MB. Files larger than 10 MB
must be compressed or split before uploading.

**What credit card networks are supported on the new platform?**
Visa, Mastercard, American Express, Discover, Diners Club, UnionPay, and JCB
are all supported. The legacy platform did not support UnionPay or JCB; if
your account has a UnionPay or JCB card on file, it will be migrated and will
become active on the new platform for the first time.

**Can I use the legacy platform to generate reports after migration?**
The legacy platform is in read-only mode for 90 days after migration. You can
view and export data from the legacy platform's reporting module during this
period. After 90 days, the legacy platform is decommissioned and reporting
is only available from the new platform.

**What happens to scheduled subscription renewals that fall during the
migration window?**
Subscription renewals that fall during the in progress phase are deferred and
processed automatically on the new platform within 4 hours of migration
completing. You will receive a renewal invoice shortly after migration
completes if a renewal was deferred.

**Can billing contacts receive migration status updates via SMS?**
SMS notifications for migration status are not currently available. Email
is the only notification channel for migration status updates. In-app banners
on the Billing Overview page also display real-time status.

**What should I do if a billing contact's email address changed just before
migration?**
Update the email address in Billing > Contacts at least 24 hours before the
migration window. Email changes take up to 24 hours to propagate. If the
migration window starts before the update propagates, the old address will
receive migration notifications.

**Are there any differences in invoice formatting between the legacy and new
platforms?**
The default invoice layout is updated on the new platform. The key changes
are: company logo placement has moved from the top right to the top left;
the invoice due date is now displayed more prominently; line item descriptions
support up to 500 characters (up from 255 on the legacy platform); and a QR
code linking to the online payment portal is included by default.

**Can I use a different currency for different subscriptions after migration?**
Yes. The new platform supports per-subscription currency assignment for
Business and Enterprise accounts. Contact billing support to configure
multi-currency subscriptions after migration.

**What is the maximum number of payment methods I can have on my account?**
The new platform supports up to 25 payment methods per account (up from 10
on the legacy platform). All payment methods from the legacy platform will
be migrated regardless of this limit; the limit applies only to methods added
after migration.

**Will the migration affect my NetSuite or QuickBooks integration?**
If you use an accounting integration (NetSuite, QuickBooks, Xero, or similar),
the integration will need to be re-authenticated after migration because the
billing account ID format changes. You may also see a SYNC-9001 or SYNC-9002
error code. See the integration-specific reconnection guide in Billing >
Integrations > [Integration name] > Reconnect.

---

## Appendix C: Migration Error Code Quick Reference

| Code | Series | Blocking | One-line description |
|---|---|---|---|
| ERR-4032 | Core | Yes | Required field missing from profile |
| ERR-4040 | Core | Yes | Payment method re-verification failed |
| ERR-4155 | Core | Yes | Duplicate billing profile |
| ERR-5010 | Core | No | Invoice account locked (dispute) |
| ERR-5020 | Core | No | Tax ID in unsupported legacy format |
| PAY-1001 | Payment | Yes | Default card expired |
| PAY-1002 | Payment | Yes | Issuer declined verification charge |
| PAY-1003 | Payment | Yes | Invalid ACH routing number |
| PAY-1004 | Payment | Yes | ACH micro-deposit expired |
| PAY-1007 | Payment | Yes | Tokenization timeout |
| INV-2001 | Invoice | Yes | Invoice record inconsistent |
| INV-2003 | Invoice | Yes | Overdue unpaid invoice |
| INV-2006 | Invoice | Yes | Child accounts not yet migrated |
| TAX-3001 | Tax | No | Tax ID could not be verified |
| TAX-3004 | Tax | Yes | Tax ID conflict |
| SUB-4001 | Subscription | Yes | Legacy plan has no mapping |
| SUB-4002 | Subscription | Yes | Subscription in payment-failed state |
| ACC-5001 | Account | Yes | Owner email not verified |
| ACC-5003 | Account | No | Too many billing contacts |
| ACC-5006 | Account | Yes | Account under legal hold |
| DAT-6001 | Data | Yes | Checksum mismatch |
| DAT-6005 | Data | Yes | Referential integrity violation |
| NET-7001 | Network | No | Legacy API timeout |
| NET-7002 | Network | No | New platform API timeout |
| ROLE-8001 | Role | No | Custom role cannot be mapped |
| ROLE-8003 | Role | Yes | No Account Owner assigned |
| SYNC-9001 | Sync | No | Accounting connector lost auth |

## Appendix D: Support Escalation Contacts

| Issue type | Contact | Expected response time |
|---|---|---|
| Blocking error after two retries | Billing support via Help > Contact Support | 4 business hours |
| Data integrity error (DAT-series) | Billing support — Priority queue | 2 business hours |
| Legal hold blocking migration | Account manager | 1 business day |
| Trust and safety flag | Trust and safety team via support portal | 2 business days |
| Enterprise migration scheduling | Dedicated billing operations specialist | Confirmed via email |
| Government migration coordination | Partner billing operations | Confirmed via contract |
| Security log access request | Security team via support portal | 5 business days |
