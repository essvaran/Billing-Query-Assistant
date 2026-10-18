import { publicSetting, refMeta } from '../shared/ref-data';
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

// Billing cycles and regions are catalog reference lists (billing_cycle, region).
export type Cycle = string;
export type Region = string;

export interface Plan {
  id: number;
  code: string;
  name: string;
  description: string;
  price_monthly_cents: number;
  price_annual_cents: number;
  currency: string;
  tier: 'standard' | 'premium' | 'enterprise';
  policy_version: 'refund-14d' | 'refund-30d';
  refund_days: number;
  features: string[];
  max_seats: number;
  is_active: boolean;
  sort_order: number;
}

export interface Addon {
  id: number;
  code: string;
  name: string;
  description: string;
  price_monthly_cents: number;
  is_active: boolean;
}

export interface BillingProfile {
  company_name: string;
  billing_email: string;
  address: string;
  region: Region;
  currency: string;
  billing_cycle: Cycle;
}

export interface SubscriptionAddon { addon_id: number; code: string; name: string; price_monthly_cents: number; quantity: number }

export interface Subscription {
  id: number;
  user_id: number;
  plan_id: number;
  plan_code: string;
  plan_name: string;
  billing_cycle: Cycle;
  status: 'active' | 'cancelled' | 'past_due';
  seats: number;
  started_at: string;
  current_period_end: string;
  cancelled_at: string | null;
  refund_days: number;
  addons: SubscriptionAddon[];
}

export interface InvoiceLine { kind: string; description: string; unit_cents: number; quantity: number; amount_cents: number }

export interface Invoice {
  id: number;
  user_id: number;
  email?: string;
  number: string;
  period_start: string;
  period_end: string;
  amount_cents: number;
  currency: string;
  status: 'open' | 'paid' | 'void';
  line_items: InvoiceLine[];
  issued_at: string;
  paid_at: string | null;
}

export interface SubscriptionRequest {
  plan_id: number;
  billing_cycle: Cycle;
  seats: number;
  addons: { addon_id: number; quantity: number }[];
}

/** The same arithmetic the server uses (integer cents), so the review step shows exactly what will be charged. */
export function quote(plan: Plan, cycle: Cycle, seats: number, addons: { addon: Addon; quantity: number }[]): number {
  const months = Number(refMeta<number>('billing_cycle', cycle, 'months') ?? 1);
  const unit = unitPrice(plan, cycle);
  return unit * seats + addons.reduce((sum, a) => sum + a.addon.price_monthly_cents * months * a.quantity, 0);
}

/** Price per seat for one period of a cycle: the plan's annual price, or the monthly price times the months. */
export function unitPrice(plan: Plan, cycle: Cycle): number {
  const months = Number(refMeta<number>('billing_cycle', cycle, 'months') ?? 1);
  return refMeta<string>('billing_cycle', cycle, 'price_field') === 'annual' ? plan.price_annual_cents : plan.price_monthly_cents * months;
}

/** A new billing profile with the defaults from settings. */
export function blankProfile(): BillingProfile {
  return { company_name: '', billing_email: '', address: '', region: publicSetting<string>('billing.default_region', ''),
           currency: publicSetting<string>('billing.currency', ''), billing_cycle: 'monthly' };
}

@Injectable({ providedIn: 'root' })
export class AccountService {
  constructor(private http: HttpClient) {}

  plans(): Observable<{ plans: Plan[]; addons: Addon[] }> {
    return this.http.get<{ plans: Plan[]; addons: Addon[] }>('/api/account/plans');
  }
  profile(): Observable<BillingProfile | null> { return this.http.get<BillingProfile | null>('/api/account/profile'); }
  saveProfile(body: BillingProfile): Observable<BillingProfile> {
    return this.http.put<BillingProfile>('/api/account/profile', body);
  }
  subscription(): Observable<Subscription | null> { return this.http.get<Subscription | null>('/api/account/subscription'); }
  subscribe(body: SubscriptionRequest): Observable<Subscription> {
    return this.http.post<Subscription>('/api/account/subscription', body);
  }
  change(body: SubscriptionRequest): Observable<Subscription> {
    return this.http.put<Subscription>('/api/account/subscription', body);
  }
  cancel(): Observable<Subscription> { return this.http.post<Subscription>('/api/account/subscription/cancel', {}); }
  invoices(): Observable<Invoice[]> { return this.http.get<Invoice[]>('/api/account/invoices'); }
}
