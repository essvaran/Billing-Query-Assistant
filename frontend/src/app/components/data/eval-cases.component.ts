import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CatalogService, EvalCaseRow } from '../../services/catalog.service';
import { ModalComponent } from '../../shared/modal.component';
import { EmptyStateComponent, ErrorStateComponent } from '../../shared/primitives';
import { ToastService } from '../../shared/toast';
import { DATA_STYLES, apiMessage } from './data-shared';

const SUITES = [
  { value: 'main', label: 'Tier-1 main suite' }, { value: 'holdout', label: 'Tier-1 held-out' },
  { value: 'regression', label: 'Tier-1 regression (from reports)' }, { value: 'docs', label: 'Docs eval set (Week 6)' },
];

/** Eval cases: the tests every evaluation run uses. Switched-off cases stay stored but do not run. */
@Component({
  selector: 'app-eval-cases-admin',
  standalone: true,
  imports: [FormsModule, ModalComponent, EmptyStateComponent, ErrorStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="bar">
      <label class="sr-only" for="suite">Suite</label>
      <select id="suite" class="t1-select" [ngModel]="suite()" (ngModelChange)="suite.set($event); load()">
        @for (s of suites; track s.value) { <option [value]="s.value">{{ s.label }}</option> }
      </select>
      <input class="t1-input" type="search" placeholder="Find a case" [ngModel]="q()" (ngModelChange)="q.set($event)" aria-label="Find a case" />
      <span class="grow"></span>
      <button type="button" class="t1-btn t1-btn--primary" (click)="open(null)">Add case</button>
    </div>
    @if (error()) { <app-error-state message="Cases could not be loaded." retryLabel="Try again" (retry)="load()" /> }
    @else if (!visible().length) { <app-empty-state title="No cases" detail="Nothing in this suite matches." /> }
    @else {
      <p class="muted small">{{ visible().length }} cases, {{ activeCount() }} switched on.</p>
      <div class="table-wrap"><table class="tbl">
        <thead><tr><th>Case</th><th>Slice</th><th>Ticket or question</th><th>Expected</th><th>Changed</th><th></th></tr></thead>
        <tbody>
          @for (c of visible(); track c.case_id) {
            <tr [class.off]="!c.active">
              <td><code>{{ c.case_id }}</code></td>
              <td>{{ c['slice'] || c['mode'] }}</td>
              <td class="small">{{ text(c) }}</td>
              <td>{{ c['expected_decision'] || c['expected_behavior'] }}</td>
              <td class="small">{{ c.updated_by }}<br />{{ c.updated_at }}</td>
              <td class="actions">
                <button type="button" class="t1-btn" (click)="open(c)">Edit</button>
                <button type="button" class="t1-btn" (click)="toggle(c)">{{ c.active ? 'Switch off' : 'Switch on' }}</button>
                <button type="button" class="t1-btn t1-btn--danger" (click)="remove(c)">Delete</button>
              </td>
            </tr>
          }
        </tbody>
      </table></div>
    }
    @if (form(); as f) {
      <app-modal [title]="f.creating ? 'Add a case' : 'Edit ' + f.case_id" (closed)="form.set(null)">
        <form class="form">
          <div class="two">
            <label>Case id <input class="t1-input" name="id" [(ngModel)]="f.case_id" [disabled]="!f.creating" placeholder="Leave empty to number it" /></label>
            <label>Suite <select class="t1-select" name="suite" [(ngModel)]="f.suite">
              @for (s of suites; track s.value) { <option [value]="s.value">{{ s.label }}</option> }</select></label>
          </div>
          <label>Case fields (JSON). The server checks every field against the reference lists before saving.
            <textarea class="t1-input code" rows="18" name="data" [(ngModel)]="f.json"></textarea></label>
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
export class EvalCasesComponent implements OnInit {
  private api = inject(CatalogService);
  private toast = inject(ToastService);
  readonly suites = SUITES;
  suite = signal('main');
  q = signal('');
  rows = signal<EvalCaseRow[]>([]);
  error = signal(false);
  form = signal<{ creating: boolean; case_id: string; suite: string; json: string } | null>(null);
  formError = signal('');
  visible = computed(() => {
    const q = this.q().trim().toLowerCase();
    return this.rows().filter(r => !q || JSON.stringify(r).toLowerCase().includes(q));
  });
  activeCount = computed(() => this.visible().filter(r => r.active).length);

  ngOnInit(): void { this.load(); }
  load(): void {
    this.error.set(false);
    this.api.evalCases(this.suite()).subscribe({ next: r => this.rows.set(r), error: () => this.error.set(true) });
  }
  text(c: EvalCaseRow): string { return String(c['body'] ?? c['question'] ?? '').slice(0, 140); }

  private template(): Record<string, unknown> {
    return this.suite() === 'docs'
      ? { question: '', mode: '', expected_behavior: 'answer', is_regression: false, notes: '' }
      : { slice: '', ticket_id: '', customer_id: '', order_id: '', subject: '', body: '', expected_decision: 'ANSWER',
          expected_policy_version: 'none', expected_tools: [], forbidden_tools: [], gold_slug: '', expect_eligible: null,
          expected_days: null, accepted_reasons: [], accepted_decisions: [], pair_id: '', notes: '' };
  }

  open(c: EvalCaseRow | null): void {
    this.formError.set('');
    if (!c) { this.form.set({ creating: true, case_id: '', suite: this.suite(), json: JSON.stringify(this.template(), null, 2) }); return; }
    const data: Record<string, unknown> = { ...c };
    for (const k of ['case_id', 'suite', 'active', 'source', 'updated_at', 'updated_by']) delete data[k];
    this.form.set({ creating: false, case_id: c.case_id, suite: c.suite, json: JSON.stringify(data, null, 2) });
  }

  save(): void {
    const f = this.form();
    if (!f) return;
    let data: Record<string, unknown>;
    try { data = JSON.parse(f.json); } catch { this.formError.set('The case fields are not valid JSON.'); return; }
    (f.creating ? this.api.createCase(f.case_id.trim(), f.suite, data) : this.api.updateCase(f.case_id, f.suite, data)).subscribe({
      next: () => { this.form.set(null); this.toast.success('Case saved.'); this.load(); },
      error: err => this.formError.set(apiMessage(err)),
    });
  }

  toggle(c: EvalCaseRow): void {
    this.api.setCaseActive(c.case_id, !c.active).subscribe({ next: () => this.load(), error: err => this.toast.error(apiMessage(err)) });
  }

  remove(c: EvalCaseRow): void {
    if (!window.confirm(`Delete ${c.case_id}? Switching it off keeps it for later; deleting removes it.`)) return;
    this.api.deleteCase(c.case_id).subscribe({ next: () => { this.toast.success('Deleted.'); this.load(); }, error: err => this.toast.error(apiMessage(err)) });
  }
}
