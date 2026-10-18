import { ChangeDetectionStrategy, Component, Input, OnChanges, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CatalogService } from '../../services/catalog.service';
import { publicSetting, refLabel, refValues } from '../../shared/ref-data';
import { ModalComponent } from '../../shared/modal.component';
import { EmptyStateComponent, ErrorStateComponent } from '../../shared/primitives';
import { ToastService } from '../../shared/toast';
import { DATA_STYLES, apiMessage } from './data-shared';

type Kind = 'customers' | 'orders' | 'tickets';
interface Field { key: string; label: string; type: 'text' | 'number' | 'date' | 'textarea' | 'ref'; ref?: string; required?: boolean; inTable?: boolean }

const FIELDS: Record<Kind, Field[]> = {
  customers: [
    { key: 'customer_id', label: 'Customer id', type: 'text', required: true, inTable: true },
    { key: 'name', label: 'Name', type: 'text', inTable: true },
    { key: 'email', label: 'Email', type: 'text', inTable: true },
    { key: 'address', label: 'Address', type: 'textarea' },
    { key: 'region', label: 'Region', type: 'ref', ref: 'region', required: true, inTable: true },
    { key: 'plan', label: 'Plan', type: 'ref', ref: 'plan_tier', required: true, inTable: true },
    { key: 'policy_version', label: 'Refund policy', type: 'ref', ref: 'policy_version', required: true, inTable: true },
    { key: 'refund_days', label: 'Refund window (days)', type: 'number', required: true, inTable: true },
    { key: 'standard_days', label: 'Standard delivery (days)', type: 'number' },
    { key: 'express_days', label: 'Express delivery (days)', type: 'number' },
  ],
  orders: [
    { key: 'order_id', label: 'Order id', type: 'text', required: true, inTable: true },
    { key: 'customer_id', label: 'Customer id', type: 'text', required: true, inTable: true },
    { key: 'purchase_date', label: 'Purchase date', type: 'date', required: true, inTable: true },
    { key: 'amount', label: 'Amount', type: 'number', required: true, inTable: true },
    { key: 'currency', label: 'Currency', type: 'text', inTable: true },
    { key: 'status', label: 'Status', type: 'ref', ref: 'tier1_order_status', required: true, inTable: true },
  ],
  tickets: [
    { key: 'ticket_id', label: 'Ticket id', type: 'text', required: true, inTable: true },
    { key: 'customer_id', label: 'Customer id', type: 'text', required: true, inTable: true },
    { key: 'order_id', label: 'Order id', type: 'text', required: true, inTable: true },
    { key: 'kind', label: 'Kind', type: 'ref', ref: 'tier1_ticket_kind', required: true, inTable: true },
    { key: 'subject', label: 'Subject', type: 'text', inTable: true },
    { key: 'body', label: 'Ticket text', type: 'textarea', required: true },
    { key: 'expected_decision', label: 'Expected decision (ANSWER or ESCALATE, for evaluation)', type: 'text' },
    { key: 'gold_slug', label: 'Article that answers it (slug)', type: 'text' },
    { key: 'expected_policy_version', label: 'Expected refund policy', type: 'ref', ref: 'policy_version' },
  ],
};
const ID: Record<Kind, string> = { customers: 'customer_id', orders: 'order_id', tickets: 'ticket_id' };

/** Tier-1 customers, orders and tickets: the data the assistant answers from. */
@Component({
  selector: 'app-tier1-data',
  standalone: true,
  imports: [FormsModule, ModalComponent, EmptyStateComponent, ErrorStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="bar">
      <input class="t1-input" type="search" placeholder="Search" [ngModel]="q()" (ngModelChange)="q.set($event); load()" aria-label="Search" />
      <span class="grow"></span>
      <button type="button" class="t1-btn t1-btn--primary" (click)="open(null)">Add {{ singular() }}</button>
    </div>
    @if (error()) { <app-error-state message="The data could not be loaded." retryLabel="Try again" (retry)="load()" /> }
    @else if (!rows().length) { <app-empty-state title="Nothing here" detail="No record matches." /> }
    @else {
      <p class="muted small">{{ rows().length }} {{ kind }}.</p>
      <div class="table-wrap"><table class="tbl">
        <thead><tr>@for (f of tableFields(); track f.key) { <th>{{ f.label }}</th> }
          @if (kind !== 'tickets') { <th class="num">{{ kind === 'customers' ? 'Orders' : 'Tickets' }}</th> }<th></th></tr></thead>
        <tbody>
          @for (r of rows(); track r[idKey()]) {
            <tr>@for (f of tableFields(); track f.key) { <td>{{ cell(r, f) }}</td> }
              @if (kind !== 'tickets') { <td class="num">{{ r[kind === 'customers' ? 'orders' : 'tickets'] }}</td> }
              <td class="actions"><button type="button" class="t1-btn" (click)="open(r)">Edit</button>
                <button type="button" class="t1-btn t1-btn--danger" (click)="remove(r)">Delete</button></td></tr>
          }
        </tbody>
      </table></div>
    }
    @if (form(); as f) {
      <app-modal [title]="creating() ? 'Add ' + singular() : 'Edit ' + f[idKey()]" (closed)="form.set(null)">
        <form class="form">
          @for (fd of fields(); track fd.key) {
            <label>{{ fd.label }}{{ fd.required ? '' : ' (optional)' }}
              @switch (fd.type) {
                @case ('textarea') { <textarea class="t1-input" rows="3" [name]="fd.key" [(ngModel)]="f[fd.key]"></textarea> }
                @case ('number') { <input class="t1-input" type="number" step="any" [name]="fd.key" [(ngModel)]="f[fd.key]" /> }
                @case ('date') { <input class="t1-input" type="date" [name]="fd.key" [(ngModel)]="f[fd.key]" /> }
                @case ('ref') {
                  <select class="t1-select" [name]="fd.key" [(ngModel)]="f[fd.key]">
                    @if (!fd.required) { <option [ngValue]="null">None</option> }
                    @for (o of options(fd.ref!); track o.code) { <option [value]="o.code">{{ o.label }}</option> }
                  </select>
                }
                @default { <input class="t1-input" [name]="fd.key" [(ngModel)]="f[fd.key]" [disabled]="!creating() && fd.key === idKey()" /> }
              }
            </label>
          }
          @if (formError()) { <p class="err" role="alert">{{ formError() }}</p> }
        </form>
        <div modal-actions>
          <button type="button" class="t1-btn" (click)="form.set(null)">Cancel</button>
          <button type="button" class="t1-btn t1-btn--primary" (click)="save()">Save</button>
        </div>
      </app-modal>
    }
  `,
  styles: [DATA_STYLES],
})
export class Tier1DataComponent implements OnChanges {
  @Input({ required: true }) kind!: Kind;
  private api = inject(CatalogService);
  private toast = inject(ToastService);
  rows = signal<Record<string, unknown>[]>([]);
  error = signal(false);
  q = signal('');
  form = signal<Record<string, unknown> | null>(null);
  creating = signal(false);
  formError = signal('');
  private kindSig = signal<Kind>('customers');
  fields = computed(() => FIELDS[this.kindSig()]);
  tableFields = computed(() => this.fields().filter(f => f.inTable));
  idKey = computed(() => ID[this.kindSig()]);
  singular = computed(() => this.kindSig().slice(0, -1));

  ngOnChanges(): void { this.kindSig.set(this.kind); this.q.set(''); this.load(); }

  load(): void {
    this.error.set(false);
    this.api.tier1List(this.kind, this.q()).subscribe({ next: r => this.rows.set(r), error: () => this.error.set(true) });
  }

  options(category: string) { return refValues(category); }
  cell(r: Record<string, unknown>, f: Field): string {
    const v = r[f.key];
    if (f.type === 'ref') return refLabel(f.ref!, v as string);
    if (f.key === 'body') return String(v ?? '').slice(0, 100);
    return v === null || v === undefined ? '' : String(v);
  }

  open(r: Record<string, unknown> | null): void {
    this.formError.set('');
    this.creating.set(!r);
    if (r) { this.form.set({ ...r }); return; }
    const blank: Record<string, unknown> = {};
    for (const f of this.fields()) blank[f.key] = f.type === 'ref' && f.required ? (refValues(f.ref!)[0]?.code ?? '') : (f.required ? '' : null);
    if (this.kind === 'orders') blank['currency'] = publicSetting<string>('billing.currency', '');
    this.form.set(blank);
  }

  save(): void {
    const f = this.form();
    if (!f) return;
    const body: Record<string, unknown> = {};
    for (const fd of this.fields()) {
      let v = f[fd.key];
      if (fd.type === 'number' && v !== null && v !== '' && v !== undefined) v = Number(v);
      if (v === '' && !fd.required) v = null;
      if (v !== null && v !== undefined) body[fd.key] = v;
    }
    const id = String(f[this.idKey()] ?? '');
    (this.creating() ? this.api.tier1Create(this.kind, body) : this.api.tier1Update(this.kind, id, body)).subscribe({
      next: () => { this.form.set(null); this.toast.success('Saved.'); this.load(); },
      error: err => this.formError.set(apiMessage(err)),
    });
  }

  remove(r: Record<string, unknown>): void {
    const id = String(r[this.idKey()]);
    if (!window.confirm(`Delete ${id}?`)) return;
    this.api.tier1Delete(this.kind, id).subscribe({ next: () => { this.toast.success('Deleted.'); this.load(); }, error: err => this.toast.error(apiMessage(err)) });
  }
}
