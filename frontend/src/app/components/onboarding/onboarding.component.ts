import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { switchMap } from 'rxjs';
import {
  AccountService, Addon, BillingProfile, Cycle, Plan, blankProfile, quote, unitPrice,
} from '../../services/account.service';
import { AuthService } from '../../services/auth.service';
import { cycleMonths, money } from '../../shared/labels';
import { refMeta, refValues } from '../../shared/ref-data';

@Component({
  selector: 'app-onboarding',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="t1-page ob">
      <div class="t1-page__head">
        <div>
          <h1 class="t1-h1">Set up your account</h1>
          <p class="t1-sub">Three quick steps. You can change any of this later from your account page.</p>
        </div>
      </div>

      <ol class="steps" aria-label="Progress">
        @for (label of stepLabels; track label; let i = $index) {
          <li [class.on]="step === i + 1" [class.done]="step > i + 1" [attr.aria-current]="step === i + 1 ? 'step' : null">
            <span class="num">{{ i + 1 }}</span> {{ label }}
          </li>
        }
      </ol>

      @if (loading) { <p class="text-muted">Loading plans…</p> }
      @if (error) { <div class="err" role="alert">{{ error }}</div> }

      @if (!loading && step === 1) {
        <div class="cycle" role="group" aria-label="Billing cycle">
          @for (c of cycles(); track c.code) {
            <button type="button" [class.active]="cycle === c.code" (click)="cycle = c.code">{{ c.label }}</button>
          }
        </div>
        <div class="plans">
          @for (p of plans; track p.id) {
            <button type="button" class="plan" [class.sel]="plan?.id === p.id" (click)="pick(p)"
                    [attr.aria-pressed]="plan?.id === p.id">
              <h2>{{ p.name }}</h2>
              <p class="desc">{{ p.description }}</p>
              <p class="price">{{ money(unitPrice(p, cycle), p.currency) }}
                <span>per seat / {{ period(cycle) }}</span></p>
              <ul>
                @for (f of p.features; track f) { <li>{{ f }}</li> }
                <li>Up to {{ p.max_seats }} seat{{ p.max_seats === 1 ? '' : 's' }}</li>
              </ul>
            </button>
          }
        </div>
        @if (plan) {
          <div class="row">
            <label class="t1-label" for="seats">Seats</label>
            <input id="seats" class="t1-input narrow" type="number" min="1" [max]="plan.max_seats" [(ngModel)]="seats" />
            <span class="text-muted">1 to {{ plan.max_seats }} on {{ plan.name }}</span>
          </div>
        }
        <div class="actions">
          <button class="t1-btn t1-btn--primary" [disabled]="!plan || !seatsOk()" (click)="step = 2">Continue</button>
        </div>
      }

      @if (!loading && step === 2) {
        <div class="card">
          <h2>Billing profile</h2>
          <div class="grid">
            <div><label class="t1-label" for="company">Company (optional)</label>
              <input id="company" class="t1-input" [(ngModel)]="profile.company_name" maxlength="160" /></div>
            <div><label class="t1-label" for="bemail">Billing email</label>
              <input id="bemail" class="t1-input" type="email" [(ngModel)]="profile.billing_email" maxlength="254" /></div>
            <div class="wide"><label class="t1-label" for="addr">Billing address</label>
              <input id="addr" class="t1-input" [(ngModel)]="profile.address" maxlength="300" /></div>
            <div><label class="t1-label" for="region">Region</label>
              <select id="region" class="t1-select" [(ngModel)]="profile.region">
                @for (r of regions(); track r.code) { <option [value]="r.code">{{ r.label }}</option> }
              </select></div>
          </div>
        </div>
        <div class="actions">
          <button class="t1-btn" (click)="step = 1">Back</button>
          <button class="t1-btn t1-btn--primary" [disabled]="!profile.billing_email.trim()" (click)="step = 3">Continue</button>
        </div>
      }

      @if (!loading && step === 3 && plan) {
        <div class="card">
          <h2>Add-ons</h2>
          @if (!addons.length) { <p class="text-muted">No add-ons are available right now.</p> }
          @for (a of addons; track a.id) {
            <label class="addon">
              <input type="checkbox" [checked]="!!qty[a.id]" (change)="toggle(a, $any($event.target).checked)" />
              <span class="addon__name">{{ a.name }}<small>{{ a.description }}</small></span>
              <span>{{ money(a.price_monthly_cents * months(cycle)) }} / {{ period(cycle) }}</span>
              @if (qty[a.id]) {
                <input class="t1-input qty" type="number" min="1" max="10" [(ngModel)]="qty[a.id]" aria-label="Quantity" />
              }
            </label>
          }
        </div>
        <div class="card review">
          <h2>Review</h2>
          <p>{{ plan.name }} ({{ cycle }}), {{ seats }} seat{{ seats === 1 ? '' : 's' }}</p>
          @for (a of chosen(); track a.addon.id) { <p>{{ a.addon.name }} x {{ a.quantity }}</p> }
          <p class="total">Total today: <strong>{{ money(total(), plan.currency) }}</strong></p>
          <p class="text-muted">Payments are simulated. No card is charged; an invoice is recorded on your account.</p>
        </div>
        <div class="actions">
          <button class="t1-btn" (click)="step = 2">Back</button>
          <button class="t1-btn t1-btn--primary" [disabled]="busy" (click)="finish()">
            {{ busy ? 'Setting up…' : 'Confirm and start' }}
          </button>
        </div>
      }
    </div>
  `,
  styles: [`
    .ob { max-width: 980px; }
    .steps { display: flex; gap: 1.25rem; list-style: none; padding: 0; margin: 0 0 1.25rem; flex-wrap: wrap; color: var(--text-muted); font-size: .85rem; }
    .steps li { display: flex; align-items: center; gap: .45rem; }
    .steps .num { width: 1.4rem; height: 1.4rem; border-radius: 50%; display: grid; place-items: center; border: 1px solid var(--border-strong); font-size: .75rem; }
    .steps .on { color: var(--text-primary); font-weight: 600; }
    .steps .on .num { background: var(--accent); color: var(--surface-card); border-color: var(--accent); }
    .steps .done .num { background: var(--success); color: var(--surface-card); border-color: var(--success); }
    .cycle { display: inline-grid; grid-template-columns: 1fr 1fr; border: 1px solid var(--border); border-radius: var(--radius-md); overflow: hidden; margin-bottom: 1rem; }
    .cycle button { background: none; border: 0; padding: .5rem 1.2rem; color: var(--text-secondary); cursor: pointer; font: inherit; }
    .cycle .active { background: var(--accent); color: var(--surface-card); font-weight: 600; }
    .plans { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1rem; }
    .plan { text-align: left; background: var(--surface-card); border: 2px solid var(--border); border-radius: var(--radius-lg); padding: 1.1rem; color: var(--text-primary); cursor: pointer; font: inherit; }
    .plan:hover { border-color: var(--border-strong); }
    .plan.sel { border-color: var(--accent); box-shadow: var(--shadow-md); }
    .plan h2 { font-size: 1.1rem; margin: 0 0 .25rem; }
    .desc { color: var(--text-secondary); font-size: .85rem; margin: 0 0 .7rem; min-height: 2.4em; }
    .price { font-size: 1.5rem; font-weight: 700; margin: 0 0 .6rem; }
    .price span { font-size: .75rem; font-weight: 400; color: var(--text-muted); }
    .plan ul { margin: 0; padding-left: 1.1rem; font-size: .83rem; color: var(--text-secondary); display: grid; gap: .2rem; }
    .row { display: flex; align-items: center; gap: .75rem; margin-top: 1rem; flex-wrap: wrap; }
    .narrow { width: 6rem; }
    .actions { display: flex; gap: .6rem; justify-content: flex-end; margin-top: 1.25rem; }
    .card { background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 1.1rem 1.2rem; margin-bottom: 1rem; }
    .card h2 { font-size: 1rem; margin: 0 0 .8rem; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: .8rem 1rem; }
    .grid .wide { grid-column: 1 / -1; }
    .grid .t1-input, .grid .t1-select { width: 100%; box-sizing: border-box; }
    .addon { display: grid; grid-template-columns: auto 1fr auto auto; gap: .8rem; align-items: center; padding: .6rem 0; border-top: 1px solid var(--border); font-size: .9rem; }
    .addon:first-of-type { border-top: 0; }
    .addon__name { display: grid; } .addon__name small { color: var(--text-muted); font-size: .78rem; }
    .qty { width: 4.5rem; }
    .review p { margin: .25rem 0; }
    .total { font-size: 1.1rem; margin-top: .6rem !important; }
    .err { color: var(--danger); background: rgba(243,139,168,.1); border: 1px solid rgba(243,139,168,.3); border-radius: 6px; padding: .5rem .75rem; margin-bottom: 1rem; }
    @media (max-width: 640px) { .grid { grid-template-columns: 1fr; } .addon { grid-template-columns: auto 1fr; } }
  `],
})
export class OnboardingComponent implements OnInit {
  readonly stepLabels = ['Choose a plan', 'Billing profile', 'Add-ons and review'];
  regions() { return refValues('region'); }
  cycles() { return refValues('billing_cycle'); }
  months(c: string) { return cycleMonths(c); }
  period(c: string) { return refMeta<string>('billing_cycle', c, 'period') ?? c; }
  unitPrice = unitPrice;
  readonly money = money;

  step = 1;
  loading = true;
  busy = false;
  error = '';

  plans: Plan[] = [];
  addons: Addon[] = [];
  plan: Plan | null = null;
  cycle: Cycle = 'monthly';
  seats = 1;
  qty: Record<number, number> = {};
  profile: BillingProfile = {
    ...blankProfile(),
  };

  constructor(private account: AccountService, private auth: AuthService, private router: Router) {}

  ngOnInit(): void {
    this.profile.billing_email = this.auth.currentUser?.email ?? '';
    this.account.subscription().subscribe({
      next: sub => { if (sub && sub.status !== 'cancelled') this.router.navigate(['/']); },
      error: () => undefined,
    });
    this.account.plans().subscribe({
      next: res => { this.plans = res.plans; this.addons = res.addons; this.loading = false; },
      error: () => { this.error = 'Could not load plans. Refresh to try again.'; this.loading = false; },
    });
  }

  pick(p: Plan): void {
    this.plan = p;
    this.seats = Math.min(Math.max(1, this.seats), p.max_seats);
  }

  seatsOk(): boolean {
    return !!this.plan && Number.isInteger(this.seats) && this.seats >= 1 && this.seats <= this.plan.max_seats;
  }

  toggle(a: Addon, on: boolean): void {
    if (on) this.qty[a.id] = 1; else delete this.qty[a.id];
  }

  chosen(): { addon: Addon; quantity: number }[] {
    return this.addons.filter(a => this.qty[a.id]).map(a => ({ addon: a, quantity: Math.min(10, Math.max(1, +this.qty[a.id] || 1)) }));
  }

  total(): number {
    return this.plan ? quote(this.plan, this.cycle, this.seats, this.chosen()) : 0;
  }

  finish(): void {
    if (!this.plan || this.busy) return;
    this.busy = true;
    this.error = '';
    const profile = { ...this.profile, billing_cycle: this.cycle };
    const body = {
      plan_id: this.plan.id, billing_cycle: this.cycle, seats: this.seats,
      addons: this.chosen().map(a => ({ addon_id: a.addon.id, quantity: a.quantity })),
    };
    this.account.saveProfile(profile).pipe(switchMap(() => this.account.subscribe(body))).subscribe({
      next: () => this.router.navigate(['/']),
      error: err => {
        this.busy = false;
        const detail = err?.error?.detail;
        this.error = typeof detail === 'string' ? detail : (Array.isArray(detail) && detail[0]?.msg) || 'Could not finish setup. Please try again.';
      },
    });
  }
}
