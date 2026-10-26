import { Component, OnInit } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  AccountService, Addon, BillingProfile, Cycle, Invoice, Plan, Subscription, blankProfile, quote,
} from '../../services/account.service';
import { AuthService } from '../../services/auth.service';
import { ModalComponent } from '../../shared/modal.component';
import { ToastService } from '../../shared/toast';
import { cycleMonths, money } from '../../shared/labels';
import { refLabel, refValues } from '../../shared/ref-data';
import { ErrorStateComponent } from '../../shared/primitives';

@Component({
  selector: 'app-account',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, ModalComponent, ErrorStateComponent],
  template: `
    <div class="t1-page acct">
      <div class="t1-page__head">
        <div>
          <h1 class="t1-h1">Your account</h1>
          <p class="t1-sub">{{ auth.currentUser?.email }}</p>
        </div>
      </div>

      @if (loading) { <p class="text-muted">Loading…</p> }

      @if (!loading) {
        <section class="card" aria-labelledby="h-sub">
          <h2 id="h-sub">Subscription</h2>
          @if (sub && sub.status !== 'cancelled') {
            <p><strong>{{ sub.plan_name }}</strong> ({{ label('billing_cycle', sub.billing_cycle) }}), {{ sub.seats }} seat{{ sub.seats === 1 ? '' : 's' }}
              <span class="pill">{{ label('subscription_status', sub.status) }}</span></p>
            <p class="text-muted">Renews {{ sub.current_period_end | date:'mediumDate' }}. Refund window: {{ sub.refund_days }} days.</p>
            @if (sub.addons.length) {
              <p class="text-muted">Add-ons: @for (a of sub.addons; track a.addon_id; let last = $last) { {{ a.name }} x {{ a.quantity }}{{ last ? '' : ', ' }} }</p>
            }
            <div class="actions">
              @if (plansFailed) {
                <button class="t1-btn" (click)="loadPlans()">Plans did not load. Retry</button>
              } @else {
                <button class="t1-btn t1-btn--primary" [disabled]="!plans.length" (click)="startChange()">Change plan</button>
              }
              <button class="t1-btn" (click)="confirmCancel = true">Cancel subscription</button>
            </div>
          } @else {
            <p>@if (sub) { Your subscription was cancelled. } @else { You do not have a subscription yet. }</p>
            <a class="t1-btn t1-btn--primary" routerLink="/onboarding">Choose a plan</a>
          }
        </section>

        @if (changing && plan) {
          <section class="card" aria-labelledby="h-change">
            <h2 id="h-change">Change plan</h2>
            <div class="grid">
              <div><label class="t1-label" for="plan">Plan</label>
                <select id="plan" class="t1-select" [ngModel]="plan.id" (ngModelChange)="selectPlan($event)">
                  @for (p of plans; track p.id) { <option [ngValue]="p.id">{{ p.name }}</option> }
                </select></div>
              <div><label class="t1-label" for="cycle">Billing cycle</label>
                <select id="cycle" class="t1-select" [(ngModel)]="cycle">
                  @for (c of cycles(); track c.code) { <option [value]="c.code">{{ c.label }}</option> }
                </select></div>
              <div><label class="t1-label" for="seats">Seats (max {{ plan.max_seats }})</label>
                <input id="seats" class="t1-input" type="number" min="1" [max]="plan.max_seats" [(ngModel)]="seats" /></div>
            </div>
            @for (a of addons; track a.id) {
              <label class="addon">
                <input type="checkbox" [checked]="!!qty[a.id]" (change)="toggle(a, $any($event.target).checked)" />
                <span>{{ a.name }}</span>
                <span class="text-muted">{{ money(a.price_monthly_cents * months(cycle)) }}</span>
                @if (qty[a.id]) { <input class="t1-input qty" type="number" min="1" max="10" [(ngModel)]="qty[a.id]" aria-label="Quantity" /> }
              </label>
            }
            <p>New period price: <strong>{{ money(total(), plan.currency) }}</strong>
              <span class="text-muted"> (unused time on your current plan is credited)</span></p>
            <div class="actions">
              <button class="t1-btn" (click)="changing = false">Close</button>
              <button class="t1-btn t1-btn--primary" [disabled]="busy || !seatsOk()" (click)="saveChange()">Confirm change</button>
            </div>
          </section>
        }

        <section class="card" aria-labelledby="h-prof">
          <h2 id="h-prof">Billing profile</h2>
          <div class="grid">
            <div><label class="t1-label" for="company">Company</label>
              <input id="company" class="t1-input" [(ngModel)]="profile.company_name" maxlength="160" /></div>
            <div><label class="t1-label" for="bemail">Billing email</label>
              <input id="bemail" class="t1-input" type="email" [(ngModel)]="profile.billing_email" maxlength="254" /></div>
            <div><label class="t1-label" for="addr">Address</label>
              <input id="addr" class="t1-input" [(ngModel)]="profile.address" maxlength="300" /></div>
            <div><label class="t1-label" for="region">Region</label>
              <select id="region" class="t1-select" [(ngModel)]="profile.region">
                @for (r of regions(); track r.code) { <option [value]="r.code">{{ r.label }}</option> }
              </select></div>
          </div>
          <div class="actions"><button class="t1-btn t1-btn--primary" [disabled]="busy" (click)="saveProfile()">Save profile</button></div>
        </section>

        <section class="card" aria-labelledby="h-inv">
          <h2 id="h-inv">Invoices</h2>
          @if (invoicesState === 'loading') { <p class="text-muted" role="status">Loading invoices</p> }
          @else if (invoicesState === 'error') {
            <app-error-state title="Invoices did not load" message="Your invoices are safe; we could not fetch them just now."
                             retryLabel="Try again" (retry)="loadInvoices()" />
          }
          @else if (!invoices.length) { <p class="text-muted">No invoices yet.</p> } @else {
            <div class="table-wrap">
              <table class="tbl">
                <thead><tr><th>Number</th><th>Issued</th><th>Period</th><th class="num">Amount</th><th>Status</th></tr></thead>
                <tbody>
                  @for (i of invoices; track i.id) {
                    <tr>
                      <td>{{ i.number }}</td>
                      <td>{{ i.issued_at | date:'mediumDate' }}</td>
                      <td>{{ i.period_start | date:'MMM d' }} to {{ i.period_end | date:'MMM d, y' }}</td>
                      <td class="num">{{ money(i.amount_cents, i.currency) }}</td>
                      <td><span class="pill pill--{{ i.status }}">{{ label('invoice_status', i.status) }}</span></td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }
        </section>
      }

      @if (confirmCancel) {
        <app-modal title="Cancel subscription" (closed)="confirmCancel = false">
          <p>Cancel your {{ sub?.plan_name }} subscription? You can subscribe again at any time.</p>
          <ng-container modal-actions>
            <button class="t1-btn" (click)="confirmCancel = false">Keep it</button>
            <button class="t1-btn t1-btn--primary" [disabled]="busy" (click)="cancel()">Cancel subscription</button>
          </ng-container>
        </app-modal>
      }
    </div>
  `,
  styles: [`
    .acct { max-width: 900px; }
    .card { background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 1.1rem 1.2rem; margin-bottom: 1rem; }
    .card h2 { font-size: 1rem; margin: 0 0 .7rem; }
    .card p { margin: .3rem 0; }
    .actions { display: flex; gap: .6rem; justify-content: flex-end; margin-top: .9rem; flex-wrap: wrap; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: .8rem 1rem; }
    .grid .t1-input, .grid .t1-select { width: 100%; box-sizing: border-box; }
    .addon { display: grid; grid-template-columns: auto 1fr auto auto; gap: .8rem; align-items: center; padding: .5rem 0; border-top: 1px solid var(--border); font-size: .9rem; }
    .qty { width: 4.5rem; }
    .pill { font-size: .7rem; text-transform: uppercase; letter-spacing: .04em; padding: .1rem .5rem; border-radius: 999px; border: 1px solid var(--border-strong); color: var(--text-secondary); margin-left: .4rem; }
    .pill--paid { color: var(--success); border-color: var(--success); }
    .pill--void { color: var(--text-muted); } .pill--open { color: var(--warning); border-color: var(--warning); }
    .table-wrap { overflow-x: auto; }
    .tbl { width: 100%; border-collapse: collapse; font-size: .88rem; }
    .tbl th, .tbl td { text-align: left; padding: .5rem .6rem; border-bottom: 1px solid var(--border); white-space: nowrap; }
    .tbl th { color: var(--text-muted); font-size: .72rem; text-transform: uppercase; letter-spacing: .04em; }
    .tbl .num { text-align: right; }
  `],
})
export class AccountComponent implements OnInit {
  regions() { return refValues('region'); }
  cycles() { return refValues('billing_cycle'); }
  months(c: string) { return cycleMonths(c); }
  readonly money = money;

  loading = true;
  busy = false;
  sub: Subscription | null = null;
  invoices: Invoice[] = [];
  plans: Plan[] = [];
  addons: Addon[] = [];
  profile: BillingProfile = blankProfile();

  changing = false;
  confirmCancel = false;
  plan: Plan | null = null;
  cycle: Cycle = 'monthly';
  seats = 1;
  qty: Record<number, number> = {};

  constructor(private account: AccountService, public auth: AuthService, private toast: ToastService) {}

  // Load failures are shown as failures, never as an empty list ("No invoices yet" when the call failed).
  invoicesState: 'loading' | 'ok' | 'error' = 'loading';
  plansFailed = false;

  label(category: string, code: string | null | undefined): string { return refLabel(category, code, code ?? ''); }

  ngOnInit(): void {
    this.reload();
    this.account.profile().subscribe({ next: p => { if (p) this.profile = p; }, error: () => undefined });
    this.loadPlans();
  }

  loadPlans(): void {
    this.plansFailed = false;
    this.account.plans().subscribe({
      next: r => { this.plans = r.plans; this.addons = r.addons; },
      error: () => { this.plansFailed = true; },
    });
  }

  loadInvoices(): void {
    this.invoicesState = 'loading';
    this.account.invoices().subscribe({
      next: i => { this.invoices = i; this.invoicesState = 'ok'; },
      error: () => { this.invoicesState = 'error'; },
    });
  }

  reload(): void {
    this.account.subscription().subscribe({
      next: s => { this.sub = s; this.loading = false; },
      error: () => { this.loading = false; this.toast.error('Could not load your subscription.'); },
    });
    this.loadInvoices();
  }

  startChange(): void {
    if (!this.sub) return;
    this.plan = this.plans.find(p => p.id === this.sub!.plan_id) ?? this.plans[0] ?? null;
    this.cycle = this.sub.billing_cycle;
    this.seats = this.sub.seats;
    this.qty = {};
    for (const a of this.sub.addons) this.qty[a.addon_id] = a.quantity;
    this.changing = !!this.plan;
  }

  selectPlan(id: number): void {
    this.plan = this.plans.find(p => p.id === id) ?? this.plan;
    if (this.plan) this.seats = Math.min(this.seats, this.plan.max_seats);
  }

  toggle(a: Addon, on: boolean): void {
    if (on) this.qty[a.id] = 1; else delete this.qty[a.id];
  }

  private chosen(): { addon: Addon; quantity: number }[] {
    return this.addons.filter(a => this.qty[a.id]).map(a => ({ addon: a, quantity: Math.min(10, Math.max(1, +this.qty[a.id] || 1)) }));
  }

  seatsOk(): boolean {
    return !!this.plan && Number.isInteger(this.seats) && this.seats >= 1 && this.seats <= this.plan.max_seats;
  }

  total(): number {
    return this.plan ? quote(this.plan, this.cycle, this.seats, this.chosen()) : 0;
  }

  saveChange(): void {
    if (!this.plan) return;
    this.busy = true;
    this.account.change({
      plan_id: this.plan.id, billing_cycle: this.cycle, seats: this.seats,
      addons: this.chosen().map(a => ({ addon_id: a.addon.id, quantity: a.quantity })),
    }).subscribe({
      next: s => { this.busy = false; this.sub = s; this.changing = false; this.toast.success('Plan updated.'); this.reload(); },
      error: err => { this.busy = false; this.toast.error(this.detail(err, 'Could not change your plan.')); },
    });
  }

  cancel(): void {
    this.busy = true;
    this.account.cancel().subscribe({
      next: s => { this.busy = false; this.sub = s; this.confirmCancel = false; this.changing = false; this.toast.success('Subscription cancelled.'); },
      error: err => { this.busy = false; this.confirmCancel = false; this.toast.error(this.detail(err, 'Could not cancel.')); },
    });
  }

  saveProfile(): void {
    this.busy = true;
    this.account.saveProfile(this.profile).subscribe({
      next: p => { this.busy = false; this.profile = p; this.toast.success('Billing profile saved.'); },
      error: err => { this.busy = false; this.toast.error(this.detail(err, 'Could not save your profile.')); },
    });
  }

  private detail(err: any, fallback: string): string {
    const d = err?.error?.detail;
    return typeof d === 'string' ? d : (Array.isArray(d) && d[0]?.msg) || fallback;
  }
}
