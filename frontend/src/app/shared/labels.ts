import { publicSetting, refLabel, refMeta, refValues } from './ref-data';

/**
 * Label helpers. Every text here comes from the catalog reference lists (shared/ref-data.ts), which admins edit on
 * the Data page; only number formatting lives in code.
 */

export function statusLabel(status: string | null | undefined): string {
  return refLabel('ticket_status', status);
}

/** Ticket statuses that get a tab in the queue, in their stored order. */
export function queueStatuses(): string[] {
  return refValues('ticket_status').filter(v => v.meta['queue_tab']).map(v => v.code);
}

/** Reasons offered when reporting a wrong Tier-1 answer. */
export function feedbackReasons(): { value: string; label: string; hint: string }[] {
  return refValues('ticket_report_reason').map(v => ({ value: v.code, label: v.label, hint: v.description }));
}

export function policyLabel(version: string | null | undefined): string {
  return refLabel('policy_version', version || 'none');
}

export function reasonLabel(reason: string | null | undefined): string {
  return refLabel('escalation_reason', reason || 'other', refLabel('escalation_reason', 'other'));
}

/** What the customer is told when their question goes to a person, per escalation reason. */
export function customerEscalationMessage(reason: string | null | undefined): string {
  return refMeta<string>('escalation_reason', reason || 'other', 'customer_message')
    ?? refMeta<string>('escalation_reason', 'other', 'customer_message') ?? '';
}

/** Months billed per period for a billing cycle (catalog list billing_cycle). */
export function cycleMonths(cycle: string | null | undefined): number {
  return Number(refMeta<number>('billing_cycle', cycle, 'months') ?? 1);
}

export function pct(value: number | null | undefined, digits = 0): string {
  return value === null || value === undefined ? 'Not measured' : `${(value * 100).toFixed(digits)}%`;
}

export function usd(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'Not measured';
  return value < 0.01 ? `$${value.toFixed(5)}` : `$${value.toFixed(3)}`;
}

/** Money in cents; the currency defaults to the billing currency setting. */
export function money(cents: number | null | undefined, currency?: string): string {
  if (cents === null || cents === undefined) return 'Not measured';
  const cur = currency || publicSetting<string>('billing.currency', '');
  return cur
    ? new Intl.NumberFormat('en-US', { style: 'currency', currency: cur }).format(cents / 100)
    : (cents / 100).toFixed(2);
}

/** Customers grouped by refund policy, in the policy list's order (for pickers). Any policy an admin adds appears. */
export function groupByPolicy<T extends { policy_version: string }>(items: T[]): { code: string; label: string; items: T[] }[] {
  const order = refValues('policy_version', true).map(v => v.code);
  const codes = [...order, ...Array.from(new Set(items.map(i => i.policy_version))).filter(c => !order.includes(c))];
  return codes.map(code => ({ code, label: policyLabel(code), items: items.filter(i => i.policy_version === code) }))
              .filter(g => g.items.length);
}

/** The first non-retired refund policy (the default to preselect). */
export function currentPolicy(): string {
  return refValues('policy_version').find(v => v.code !== 'none' && !v.meta['retired'])?.code ?? '';
}
