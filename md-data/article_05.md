---
article_id: HC-BILL-005
product_area: account-administration
last_updated: 2026-06-15
---

# Admin Roles and Permissions During Migration

## Who Can Initiate or Confirm Migration

Only users with the **Billing Administrator** role can confirm a migration
that requires manual action. The **Account Owner** role can always confirm
migration, even if they do not also hold the Billing Administrator role.

Standard **Member** roles cannot see the migration banner and cannot confirm
migration, even if they have access to billing history.

## Role Permission Table

| Role | Can view migration status | Can confirm migration | Can retry after an error |
|---|---|---|---|
| Account Owner | Yes | Yes | Yes |
| Billing Administrator | Yes | Yes | Yes |
| Finance Viewer | Yes | No | No |
| Member | No | No | No |

## Adding a Billing Administrator During Migration

Billing Administrator role changes made while a migration is in progress take
effect immediately and do not restart or interrupt the migration. This is
different from role changes to auto-pay settings, which are paused until
migration completes.

## Multiple Billing Contacts

If an account has more than one billing contact, migration requires
confirmation from only one Billing Administrator or the Account Owner — not
all contacts. Once confirmed, the migration proceeds for the entire account,
and all billing contacts receive a completion notification.

## Related Articles

See "Billing Profile Migration Overview" for the general migration process
and prerequisites.
