---
article_id: HC-BILL-003
product_area: billing-migration
last_updated: 2026-06-10
---

# Invoice and Payment Method Migration

## What Gets Migrated

When a billing profile migrates to the new billing platform, the following
invoice and payment data moves with it:

- All invoice PDFs issued in the last 24 months.
- Saved payment methods that passed re-verification.
- Auto-pay settings, including the auto-pay payment method.
- Billing address and tax identification information.

Invoices older than 24 months are archived but not migrated. Archived
invoices remain downloadable from the legacy billing portal for 12 months
after migration.

## Payment Method Errors During Migration

| Error code | Cause | Fix |
|---|---|---|
| ERR-4040 | The legacy payment method on file could not be re-verified with the card network | Add a new payment method and set it as default before retrying migration |
| ERR-4210 | The saved payment method uses a card network no longer supported on the new billing platform | Replace the payment method with a supported card or bank transfer method |
| ERR-4310 | Auto-pay could not be re-enabled because the associated payment method failed migration | Re-enable auto-pay manually after adding a working payment method |

## Auto-Pay Behavior After Migration

Auto-pay is paused automatically during migration and does not resume until
the account owner confirms the new default payment method. This is
intentional, to prevent a charge attempt against a payment method that failed
re-verification.

## Invoice Numbering

Invoice numbers issued before migration keep their original format. Invoice
numbers issued after migration follow the new billing platform's numbering
scheme. Both formats remain valid for accounting and tax purposes.

## Related Articles

See "Billing Migration Error Codes and Fixes" for the full list of
migration-blocking error codes, and "Invoice Numbering Changes After
Migration" for details on how the new numbering scheme is structured.
