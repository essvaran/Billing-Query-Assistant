import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Addon, Invoice, Plan, Subscription, SubscriptionRequest } from './account.service';

export interface PlanInput {
  code?: string;
  name: string;
  description: string;
  price_monthly_cents: number;
  price_annual_cents: number;
  currency: string;
  tier: string;
  policy_version: string;
  refund_days: number;
  features: string[];
  max_seats: number;
  is_active: boolean;
  sort_order: number;
}

export interface AddonInput {
  code?: string;
  name: string;
  description: string;
  price_monthly_cents: number;
  is_active: boolean;
}

export interface AuditEvent { id: number; actor_email: string; action: string; target: string; details: Record<string, unknown>; created_at: string }

export interface Dashboard {
  users_total: number;
  users_disabled: number;
  active_subscriptions: number;
  subscriptions_by_plan: { code: string; name: string; subscribers: number }[];
  mrr_cents: number;
  signups_7d: number;
  signups_30d: number;
  cancellations_30d: number;
  revenue_30d_cents: number;
  open_invoices: number;
  activity: AuditEvent[];
}

export interface AdminSubscription extends Omit<Subscription, 'addons' | 'refund_days' | 'plan_code'> { email: string }

@Injectable({ providedIn: 'root' })
export class AdminBillingService {
  private base = '/api/admin';
  constructor(private http: HttpClient) {}

  dashboard(): Observable<Dashboard> { return this.http.get<Dashboard>(`${this.base}/dashboard`); }

  plans(): Observable<Plan[]> { return this.http.get<Plan[]>(`${this.base}/plans`); }
  createPlan(body: PlanInput): Observable<Plan> { return this.http.post<Plan>(`${this.base}/plans`, body); }
  updatePlan(id: number, body: Partial<PlanInput>): Observable<Plan> { return this.http.put<Plan>(`${this.base}/plans/${id}`, body); }
  archivePlan(id: number): Observable<Plan> { return this.http.post<Plan>(`${this.base}/plans/${id}/archive`, {}); }

  addons(): Observable<Addon[]> { return this.http.get<Addon[]>(`${this.base}/addons`); }
  createAddon(body: AddonInput): Observable<Addon> { return this.http.post<Addon>(`${this.base}/addons`, body); }
  updateAddon(id: number, body: Partial<AddonInput>): Observable<Addon> { return this.http.put<Addon>(`${this.base}/addons/${id}`, body); }

  subscriptions(): Observable<AdminSubscription[]> { return this.http.get<AdminSubscription[]>(`${this.base}/subscriptions`); }
  setUserPlan(userId: number, body: SubscriptionRequest): Observable<Subscription> {
    return this.http.put<Subscription>(`${this.base}/users/${userId}/subscription`, body);
  }
  charge(userId: number, amountCents: number, description: string): Observable<Invoice> {
    return this.http.post<Invoice>(`${this.base}/users/${userId}/invoices`, { amount_cents: amountCents, description });
  }

  invoices(status = ''): Observable<Invoice[]> {
    let params = new HttpParams();
    if (status) params = params.set('status', status);
    return this.http.get<Invoice[]>(`${this.base}/invoices`, { params });
  }
  markPaid(id: number): Observable<Invoice> { return this.http.post<Invoice>(`${this.base}/invoices/${id}/mark-paid`, {}); }
  voidInvoice(id: number): Observable<Invoice> { return this.http.post<Invoice>(`${this.base}/invoices/${id}/void`, {}); }
}
