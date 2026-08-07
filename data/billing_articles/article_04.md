---
article_id: HC-BILL-004
product_area: invoicing
last_updated: 2026-06-12
---

# Invoice Numbering Changes After Migration

## Why Invoice Numbering Changed

The new billing platform issues invoice numbers in a different format than
the legacy platform so that invoice numbers stay globally unique across all
regions the platform serves. This change applies only to invoices issued
after your account's migration completes.

## Legacy Format

Legacy invoice numbers used the format:

```text
INV-<account-number>-<sequence>
```

Example: `INV-88213-0047`

## New Format

New invoice numbers use the format:

```text
<region-code>-<year>-<sequence>
```

Example: `US-2026-004821`

## Do Old Invoice Numbers Still Work?

Yes. Invoice numbers issued before migration remain valid indefinitely for
accounting, audit, and tax filing purposes. You do not need to reissue or
relabel old invoices.

## Common Numbering Questions

| Question | Answer |
|---|---|
| Will my invoice number change on invoices already sent to customers? | No, previously issued invoice numbers never change |
| Can I keep using the legacy format going forward? | No, all invoices issued after migration use the new format automatically |
| Does the new format affect tax reporting? | No, tax authorities accept either format as a valid invoice identifier |

## Where to Find This Setting

Invoice numbering format is not configurable per account. It is determined
entirely by whether the invoice was issued before or after your account's
billing profile migration completed.
