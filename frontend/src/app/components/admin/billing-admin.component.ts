import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Addon, Cycle, Invoice, Plan } from '../../services/account.service';
import {
  AddonInput, AdminBillingService, AdminSubscription, Dashboard, PlanInput,
} from '../../services/admin-billing.service';
import { KpiTileComponent, EmptyStateComponent } from '../../shared/primitives';
import { ModalComponent } from '../../shared/modal.component';
import { ToastService } from '../../shared/toast';
import { ConfirmService } from '../../shared/confirm';
import { money } from '../../shared/labels';
import { publicSetting, refMeta, refValues } from '../../shared/ref-data';

type Sub = 'dashboard' | 'plans' | 'addons' | 'subscriptions' | 'invoices';

interface PlanForm {
  id: number | null; code: string; name: string; description: string; monthly: number; annual: number;
  tier: string; policy_version: string; refund_days: number; max_seats: number; features: string;
  sort_order: number; is_active: boolean;
}
interface AddonForm { id: number | null; code: string; name: string; description: string; monthly: number; is_active: boolean }

const dollars = (cents: number) => Math.round(cents) / 100;
const cents = (d: number) => Math.round((Number(d) || 0) * 100);

@Component({
  selector: 'app-billing-admin',
  standalone: true,
  imports: [CommonModule, FormsModule, KpiTileComponent, EmptyStateComponent, ModalComponent],
  template: `
    <div class="bill">
      <div class="subtabs" role="tablist">
        @for (t of subtabs; track t.key) {
          <button role="tab" type="button" [class.active]="sub === t.key" [attr.aria-selected]="sub === t.key"
                  (click)="open(t.key)">{{ t.label }}</button>
        }
        <span class="grow"></span>
        <button class="t1-btn" type="button" (click)="refresh()">Refresh</button>
      </div>

      @if (sub === 'dashboard' && dash) {
        <div class="kpis">
          <app-kpi-tile label="Users" [value]="'' + dash.users_total" [hint]="dash.users_disabled + ' disabled'" />
          <app-kpi-tile label="Active subscriptions" [value]="'' + dash.active_subscriptions" />
          <app-kpi-tile label="Monthly recurring revenue" [value]="money(dash.mrr_cents)" />
          <app-kpi-tile label="Revenue, 30 days" [value]="money(dash.revenue_30d_cents)" />
          <app-kpi-tile label="Signups" [value]="'' + dash.signups_7d" [hint]="dash.signups_30d + ' in 30 days'" />
          <app-kpi-tile label="Cancellations, 30 days" [value]="'' + dash.cancellations_30d"
                        [tone]="dash.cancellations_30d ? 'warn' : ''" />
          <app-kpi-tile label="Open invoices" [value]="'' + dash.open_invoices" [tone]="dash.open_invoices ? 'warn' : ''" />
        </div>
        <div class="two">
          <section class="card">
            <h3>Subscribers by plan</h3>
            @for (p of dash.subscriptions_by_plan; track p.code) {
              <p class="line"><span>{{ p.name }}</span><strong>{{ p.subscribers }}</strong></p>
            } @empty { <p class="text-muted">No active subscriptions yet.</p> }
          </section>
          <section class="card">
            <h3>Recent activity <small class="text-muted">(updates every 30 seconds)</small></h3>
            <ul class="feed">
              @for (e of dash.activity; track e.id) {
                <li><span class="when">{{ e.created_at | date:'MMM d, HH:mm' }}</span>
                  <strong>{{ e.action }}</strong> {{ e.target }} <span class="text-muted">by {{ e.actor_email }}</span></li>
              } @empty { <li class="text-muted">Nothing yet.</li> }
            </ul>
          </section>
        </div>
      }

      @if (sub === 'plans') {
        <div class="bar"><button class="t1-btn t1-btn--primary" (click)="newPlan()">New plan</button></div>
        <div class="table-wrap"><table class="tbl">
          <thead><tr><th>Name</th><th>Code</th><th class="num">Monthly</th><th class="num">Annual</th><th>Tier</th><th>Refund</th><th>Seats</th><th>Status</th><th></th></tr></thead>
          <tbody>
            @for (p of plans; track p.id) {
              <tr>
                <td>{{ p.name }}</td><td class="mono">{{ p.code }}</td>
                <td class="num">{{ money(p.price_monthly_cents, p.currency) }}</td>
                <td class="num">{{ money(p.price_annual_cents, p.currency) }}</td>
                <td>{{ p.tier }}</td><td>{{ p.refund_days }}d ({{ p.policy_version }})</td><td>{{ p.max_seats }}</td>
                <td>{{ p.is_active ? 'Active' : 'Archived' }}</td>
                <td class="acts">
                  <button class="t1-btn" (click)="editPlan(p)">Edit</button>
                  @if (p.is_active) { <button class="t1-btn" (click)="archive(p)">Archive</button> }
                </td>
              </tr>
            }
          </tbody></table></div>
      }

      @if (sub === 'addons') {
        <div class="bar"><button class="t1-btn t1-btn--primary" (click)="newAddon()">New add-on</button></div>
        <div class="table-wrap"><table class="tbl">
          <thead><tr><th>Name</th><th>Code</th><th class="num">Monthly</th><th>Status</th><th></th></tr></thead>
          <tbody>
            @for (a of addons; track a.id) {
              <tr>
                <td>{{ a.name }}<div class="text-muted small">{{ a.description }}</div></td><td class="mono">{{ a.code }}</td>
                <td class="num">{{ money(a.price_monthly_cents) }}</td><td>{{ a.is_active ? 'Active' : 'Hidden' }}</td>
                <td class="acts"><button class="t1-btn" (click)="editAddon(a)">Edit</button></td>
              </tr>
            }
          </tbody></table></div>
      }

      @if (sub === 'subscriptions') {
        @if (!subs.length) { <app-empty-state title="No subscriptions yet" detail="They appear here as customers choose a plan." /> }
        @else {
          <div class="table-wrap"><table class="tbl">
            <thead><tr><th>Customer</th><th>Plan</th><th>Cycle</th><th>Seats</th><th>Status</th><th>Renews</th><th></th></tr></thead>
            <tbody>
              @for (s of subs; track s.id) {
                <tr>
                  <td>{{ s.email }}</td><td>{{ s.plan_name }}</td><td>{{ s.billing_cycle }}</td><td>{{ s.seats }}</td>
                  <td>{{ s.status }}</td><td>{{ s.current_period_end | date:'mediumDate' }}</td>
                  <td class="acts">
                    <button class="t1-btn" (click)="startOverride(s)">Set plan</button>
                    <button class="t1-btn" (click)="startCharge(s)">Charge</button>
                  </td>
                </tr>
              }
            </tbody></table></div>
        }
      }

      @if (sub === 'invoices') {
        <div class="bar">
          <label class="t1-label" for="inv-status">Status</label>
          <select id="inv-status" class="t1-select" [(ngModel)]="invStatus" (ngModelChange)="loadInvoices()">
            <option value="">All</option>
            @for (st of refValues('invoice_status'); track st.code) { <option [value]="st.code">{{ st.label }}</option> }
          </select>
        </div>
        @if (!invoices.length) { <app-empty-state title="No invoices" detail="Nothing matches this filter." /> }
        @else {
          <div class="table-wrap"><table class="tbl">
            <thead><tr><th>Number</th><th>Customer</th><th>Issued</th><th class="num">Amount</th><th>Status</th><th></th></tr></thead>
            <tbody>
              @for (i of invoices; track i.id) {
                <tr>
                  <td>{{ i.number }}</td><td>{{ i.email }}</td><td>{{ i.issued_at | date:'mediumDate' }}</td>
                  <td class="num">{{ money(i.amount_cents, i.currency) }}</td><td>{{ i.status }}</td>
                  <td class="acts">
                    @if (i.status === 'open') {
                      <button class="t1-btn" (click)="markPaid(i)">Mark paid</button>
                      <button class="t1-btn" (click)="voidInvoice(i)">Void</button>
                    }
                  </td>
                </tr>
              }
            </tbody></table></div>
        }
      }

      @if (planForm) {
        <app-modal [title]="planForm.id ? 'Edit plan' : 'New plan'" (closed)="planForm = null">
          <div class="form">
            @if (!planForm.id) {
              <label class="t1-label" for="pf-code">Code (lowercase, no spaces)</label>
              <input id="pf-code" class="t1-input" [(ngModel)]="planForm.code" />
            }
            <label class="t1-label" for="pf-name">Name</label><input id="pf-name" class="t1-input" [(ngModel)]="planForm.name" />
            <label class="t1-label" for="pf-desc">Description</label><input id="pf-desc" class="t1-input" [(ngModel)]="planForm.description" />
            <div class="pair">
              <div><label class="t1-label" for="pf-m">Monthly price ({{ currency() }} per seat)</label><input id="pf-m" class="t1-input" type="number" min="0" step="0.01" [(ngModel)]="planForm.monthly" /></div>
              <div><label class="t1-label" for="pf-a">Annual price ({{ currency() }} per seat)</label><input id="pf-a" class="t1-input" type="number" min="0" step="0.01" [(ngModel)]="planForm.annual" /></div>
              <div><label class="t1-label" for="pf-t">Tier</label>
                <select id="pf-t" class="t1-select" [(ngModel)]="planForm.tier">@for (t of refValues('plan_tier'); track t.code) { <option [value]="t.code">{{ t.label }}</option> }</select></div>
              <div><label class="t1-label" for="pf-p">Refund policy</label>
                <select id="pf-p" class="t1-select" [(ngModel)]="planForm.policy_version" (ngModelChange)="onPolicy($event)">@for (p of policies(); track p.code) { <option [value]="p.code">{{ p.label }}</option> }</select></div>
              <div><label class="t1-label" for="pf-r">Refund days</label><input id="pf-r" class="t1-input" type="number" min="1" [(ngModel)]="planForm.refund_days" /></div>
              <div><label class="t1-label" for="pf-s">Max seats</label><input id="pf-s" class="t1-input" type="number" min="1" [(ngModel)]="planForm.max_seats" /></div>
              <div><label class="t1-label" for="pf-o">Sort order</label><input id="pf-o" class="t1-input" type="number" [(ngModel)]="planForm.sort_order" /></div>
              <div class="chk"><label><input type="checkbox" [(ngModel)]="planForm.is_active" /> Available to new customers</label></div>
            </div>
            <label class="t1-label" for="pf-f">Features (one per line)</label>
            <textarea id="pf-f" class="t1-textarea" rows="4" [(ngModel)]="planForm.features"></textarea>
            <p class="text-muted small">Changing a price affects new invoices only. Existing invoices keep what was charged.</p>
          </div>
          <ng-container modal-actions>
            <button class="t1-btn" (click)="planForm = null">Cancel</button>
            <button class="t1-btn t1-btn--primary" [disabled]="busy" (click)="savePlan()">Save</button>
          </ng-container>
        </app-modal>
      }

      @if (addonForm) {
        <app-modal [title]="addonForm.id ? 'Edit add-on' : 'New add-on'" (closed)="addonForm = null">
          <div class="form">
            @if (!addonForm.id) {
              <label class="t1-label" for="af-code">Code</label><input id="af-code" class="t1-input" [(ngModel)]="addonForm.code" />
            }
            <label class="t1-label" for="af-name">Name</label><input id="af-name" class="t1-input" [(ngModel)]="addonForm.name" />
            <label class="t1-label" for="af-desc">Description</label><input id="af-desc" class="t1-input" [(ngModel)]="addonForm.description" />
            <label class="t1-label" for="af-m">Monthly price ({{ currency() }})</label>
            <input id="af-m" class="t1-input" type="number" min="0" step="0.01" [(ngModel)]="addonForm.monthly" />
            <label><input type="checkbox" [(ngModel)]="addonForm.is_active" /> Available to customers</label>
          </div>
          <ng-container modal-actions>
            <button class="t1-btn" (click)="addonForm = null">Cancel</button>
            <button class="t1-btn t1-btn--primary" [disabled]="busy" (click)="saveAddon()">Save</button>
          </ng-container>
        </app-modal>
      }

      @if (override) {
        <app-modal [title]="'Set plan for ' + override.email" (closed)="override = null">
          <div class="form">
            <label class="t1-label" for="ov-plan">Plan</label>
            <select id="ov-plan" class="t1-select" [(ngModel)]="override.plan_id">
              @for (p of activePlans(); track p.id) { <option [ngValue]="p.id">{{ p.name }}</option> }
            </select>
            <label class="t1-label" for="ov-cycle">Billing cycle</label>
            <select id="ov-cycle" class="t1-select" [(ngModel)]="override.cycle"><option value="monthly">Monthly</option><option value="annual">Annual</option></select>
            <label class="t1-label" for="ov-seats">Seats</label>
            <input id="ov-seats" class="t1-input" type="number" min="1" [(ngModel)]="override.seats" />
            <p class="text-muted small">Add-ons are cleared by this override. The customer is invoiced for the new plan.</p>
          </div>
          <ng-container modal-actions>
            <button class="t1-btn" (click)="override = null">Cancel</button>
            <button class="t1-btn t1-btn--primary" [disabled]="busy" (click)="saveOverride()">Apply</button>
          </ng-container>
        </app-modal>
      }

      @if (charge) {
        <app-modal [title]="'Manual charge for ' + charge.email" (closed)="charge = null">
          <div class="form">
            <label class="t1-label" for="ch-amt">Amount ({{ currency() }})</label>
            <input id="ch-amt" class="t1-input" type="number" min="0.01" step="0.01" [(ngModel)]="charge.amount" />
            <label class="t1-label" for="ch-desc">Description</label>
            <input id="ch-desc" class="t1-input" [(ngModel)]="charge.description" maxlength="200" />
            <p class="text-muted small">Creates an open invoice. Mark it paid from the Invoices tab.</p>
          </div>
          <ng-container modal-actions>
            <button class="t1-btn" (click)="charge = null">Cancel</button>
            <button class="t1-btn t1-btn--primary" [disabled]="busy" (click)="saveCharge()">Create invoice</button>
          </ng-container>
        </app-modal>
      }
    </div>
  `,
  styles: [`
    .bill { padding: .5rem 0 2rem; }
    .subtabs { display: flex; gap: .4rem; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; }
    .subtabs button[role=tab] { background: none; border: 1px solid var(--border); border-radius: 999px; padding: .35rem .9rem; color: var(--text-secondary); cursor: pointer; font: inherit; font-size: .85rem; }
    .subtabs button.active { background: var(--accent); border-color: var(--accent); color: var(--surface-card); font-weight: 600; }
    .grow { flex: 1; }
    .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: .8rem; margin-bottom: 1rem; }
    .two { display: grid; grid-template-columns: 1fr 2fr; gap: 1rem; }
    @media (max-width: 800px) { .two { grid-template-columns: 1fr; } }
    .card { background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 1rem 1.1rem; }
    .card h3 { font-size: .95rem; margin: 0 0 .6rem; }
    .line { display: flex; justify-content: space-between; margin: .3rem 0; }
    .feed { list-style: none; margin: 0; padding: 0; max-height: 22rem; overflow: auto; font-size: .85rem; display: grid; gap: .35rem; }
    .when { color: var(--text-muted); margin-right: .5rem; font-family: var(--font-mono); font-size: .75rem; }
    .bar { display: flex; gap: .6rem; align-items: center; margin-bottom: .8rem; }
    .table-wrap { overflow-x: auto; }
    .tbl { width: 100%; border-collapse: collapse; font-size: .88rem; }
    .tbl th, .tbl td { text-align: left; padding: .5rem .6rem; border-bottom: 1px solid var(--border); vertical-align: top; }
    .tbl th { color: var(--text-muted); font-size: .72rem; text-transform: uppercase; letter-spacing: .04em; white-space: nowrap; }
    .num { text-align: right !important; white-space: nowrap; } .mono { font-family: var(--font-mono); font-size: .8rem; }
    .acts { white-space: nowrap; display: flex; gap: .4rem; }
    .small { font-size: .78rem; margin: .2rem 0 0; }
    .form { display: grid; gap: .35rem; } .form .t1-input, .form .t1-select, .form .t1-textarea { width: 100%; box-sizing: border-box; margin-bottom: .4rem; }
    .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 0 .8rem; } .chk { align-self: end; padding-bottom: .6rem; }
  `],
})
export class BillingAdminComponent implements OnInit, OnDestroy {
  refValues = refValues;
  currency(): string { return publicSetting<string>('billing.currency', ''); }
  policies() { return refValues('policy_version').filter(v => v.code !== 'none'); }
  /** Picking a policy fills in its refund window; an admin can still change it. */
  onPolicy(code: string): void { if (this.planForm) this.planForm.refund_days = Number(refMeta<number>('policy_version', code, 'refund_days') ?? this.planForm.refund_days); }

  readonly money = money;
  readonly subtabs: { key: Sub; label: string }[] = [
    { key: 'dashboard', label: 'Dashboard' }, { key: 'plans', label: 'Plans' }, { key: 'addons', label: 'Add-ons' },
    { key: 'subscriptions', label: 'Subscriptions' }, { key: 'invoices', label: 'Invoices' },
  ];

  sub: Sub = 'dashboard';
  busy = false;
  dash: Dashboard | null = null;
  plans: Plan[] = [];
  addons: Addon[] = [];
  subs: AdminSubscription[] = [];
  invoices: Invoice[] = [];
  invStatus = '';

  planForm: PlanForm | null = null;
  addonForm: AddonForm | null = null;
  override: { user_id: number; email: string; plan_id: number; cycle: Cycle; seats: number } | null = null;
  charge: { user_id: number; email: string; amount: number; description: string } | null = null;

  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(private api: AdminBillingService, private toast: ToastService) {}

  ngOnInit(): void {
    this.refresh();
    // The dashboard is the only view that goes stale on its own, so only it polls.
    this.timer = setInterval(() => { if (this.sub === 'dashboard' && !document.hidden) this.loadDashboard(); }, 30_000);
  }

  ngOnDestroy(): void { if (this.timer) clearInterval(this.timer); }

  open(tab: Sub): void { this.sub = tab; this.refresh(); }

  refresh(): void {
    switch (this.sub) {
      case 'dashboard': this.loadDashboard(); break;
      case 'plans': this.loadPlans(); break;
      case 'addons': this.loadAddons(); break;
      case 'subscriptions': this.api.subscriptions().subscribe({ next: s => (this.subs = s), error: e => this.fail(e, 'Could not load subscriptions.') }); this.loadPlans(); break;
      case 'invoices': this.loadInvoices(); break;
    }
  }

  private loadDashboard(): void { this.api.dashboard().subscribe({ next: d => (this.dash = d), error: e => this.fail(e, 'Could not load the dashboard.') }); }
  private loadPlans(): void { this.api.plans().subscribe({ next: p => (this.plans = p), error: e => this.fail(e, 'Could not load plans.') }); }
  private loadAddons(): void { this.api.addons().subscribe({ next: a => (this.addons = a), error: e => this.fail(e, 'Could not load add-ons.') }); }
  loadInvoices(): void { this.api.invoices(this.invStatus).subscribe({ next: i => (this.invoices = i), error: e => this.fail(e, 'Could not load invoices.') }); }
  activePlans(): Plan[] { return this.plans.filter(p => p.is_active); }

  // plans
  newPlan(): void {
    const tier = refValues('plan_tier')[0]?.code ?? '';
    const policy = this.policies()[0]?.code ?? '';
    this.planForm = { id: null, code: '', name: '', description: '', monthly: 0, annual: 0, tier,
      policy_version: policy, refund_days: Number(refMeta<number>('policy_version', policy, 'refund_days') ?? 0), max_seats: 1, features: '',
      sort_order: this.plans.length + 1, is_active: true };
  }
  editPlan(p: Plan): void {
    this.planForm = { id: p.id, code: p.code, name: p.name, description: p.description, monthly: dollars(p.price_monthly_cents),
      annual: dollars(p.price_annual_cents), tier: p.tier, policy_version: p.policy_version, refund_days: p.refund_days,
      max_seats: p.max_seats, features: p.features.join('\n'), sort_order: p.sort_order, is_active: p.is_active };
  }
  savePlan(): void {
    const f = this.planForm;
    if (!f) return;
    const body: PlanInput = {
      name: f.name.trim(), description: f.description.trim(), price_monthly_cents: cents(f.monthly), price_annual_cents: cents(f.annual),
      currency: this.currency(), tier: f.tier, policy_version: f.policy_version, refund_days: +f.refund_days, max_seats: +f.max_seats,
      features: f.features.split('\n').map(x => x.trim()).filter(Boolean), is_active: f.is_active, sort_order: +f.sort_order,
    };
    if (!body.name) { this.toast.error('Give the plan a name.'); return; }
    this.busy = true;
    const req = f.id ? this.api.updatePlan(f.id, body) : this.api.createPlan({ ...body, code: f.code.trim() });
    req.subscribe({
      next: () => { this.busy = false; this.planForm = null; this.toast.success('Plan saved.'); this.loadPlans(); },
      error: e => { this.busy = false; this.fail(e, 'Could not save the plan.'); },
    });
  }
  async archive(p: Plan): Promise<void> {
    if (!(await this.confirm.ask(`Archive ${p.name}? New customers can no longer choose it; current subscribers keep it.`, { confirmLabel: 'Archive' }))) return;
    this.api.archivePlan(p.id).subscribe({
      next: () => { this.toast.success(`${p.name} archived. Current subscribers keep it.`); this.loadPlans(); },
      error: e => this.fail(e, 'Could not archive the plan.'),
    });
  }

  // add-ons
  newAddon(): void { this.addonForm = { id: null, code: '', name: '', description: '', monthly: 0, is_active: true }; }
  editAddon(a: Addon): void {
    this.addonForm = { id: a.id, code: a.code, name: a.name, description: a.description, monthly: dollars(a.price_monthly_cents), is_active: a.is_active };
  }
  saveAddon(): void {
    const f = this.addonForm;
    if (!f) return;
    const body: AddonInput = { name: f.name.trim(), description: f.description.trim(), price_monthly_cents: cents(f.monthly), is_active: f.is_active };
    if (!body.name) { this.toast.error('Give the add-on a name.'); return; }
    this.busy = true;
    const req = f.id ? this.api.updateAddon(f.id, body) : this.api.createAddon({ ...body, code: f.code.trim() });
    req.subscribe({
      next: () => { this.busy = false; this.addonForm = null; this.toast.success('Add-on saved.'); this.loadAddons(); },
      error: e => { this.busy = false; this.fail(e, 'Could not save the add-on.'); },
    });
  }

  // subscriptions
  startOverride(s: AdminSubscription): void {
    this.override = { user_id: s.user_id, email: s.email, plan_id: s.plan_id, cycle: s.billing_cycle, seats: s.seats };
  }
  saveOverride(): void {
    const o = this.override;
    if (!o) return;
    this.busy = true;
    this.api.setUserPlan(o.user_id, { plan_id: o.plan_id, billing_cycle: o.cycle, seats: +o.seats, addons: [] }).subscribe({
      next: () => { this.busy = false; this.override = null; this.toast.success('Plan updated.'); this.refresh(); },
      error: e => { this.busy = false; this.fail(e, 'Could not change the plan.'); },
    });
  }
  startCharge(s: AdminSubscription): void { this.charge = { user_id: s.user_id, email: s.email, amount: 0, description: '' }; }
  saveCharge(): void {
    const c = this.charge;
    if (!c) return;
    if (cents(c.amount) <= 0 || !c.description.trim()) { this.toast.error('Enter an amount and a description.'); return; }
    this.busy = true;
    this.api.charge(c.user_id, cents(c.amount), c.description.trim()).subscribe({
      next: () => { this.busy = false; this.charge = null; this.toast.success('Invoice created.'); },
      error: e => { this.busy = false; this.fail(e, 'Could not create the invoice.'); },
    });
  }

  // invoices
  private readonly confirm = inject(ConfirmService);

  async markPaid(i: Invoice): Promise<void> {
    if (!(await this.confirm.ask(`Mark invoice ${i.number} (${this.money(i.amount_cents, i.currency)}) as paid?`, { confirmLabel: 'Mark paid' }))) return;
    this.api.markPaid(i.id).subscribe({ next: () => { this.toast.success(`${i.number} marked paid.`); this.loadInvoices(); }, error: e => this.fail(e, 'Could not update the invoice.') });
  }
  async voidInvoice(i: Invoice): Promise<void> {
    if (!(await this.confirm.ask(`Void invoice ${i.number}? The customer will no longer owe it, and this cannot be undone.`, { danger: true, confirmLabel: 'Void invoice' }))) return;
    this.api.voidInvoice(i.id).subscribe({ next: () => { this.toast.success(`${i.number} voided.`); this.loadInvoices(); }, error: e => this.fail(e, 'Could not void the invoice.') });
  }

  private fail(err: any, fallback: string): void {
    const d = err?.error?.detail;
    this.toast.error(typeof d === 'string' ? d : (Array.isArray(d) && d[0]?.msg) || fallback, err);
  }
}
