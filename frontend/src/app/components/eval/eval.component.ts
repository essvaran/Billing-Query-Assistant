import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { CatalogService, Week6, Week6Row } from '../../services/catalog.service';
import { refLabel } from '../../shared/ref-data';
import { EmptyStateComponent, ErrorStateComponent } from '../../shared/primitives';
import { ToastService } from '../../shared/toast';

/**
 * The Week 6 evaluation of the Docs pipeline, read from the stored run (catalog run 'week6'): cases, assertion
 * results, both judge rubrics, the human labels and the agreement computed from them. Nothing on this page is typed
 * into the code; the notes are editable.
 */
@Component({
  selector: 'app-eval',
  standalone: true,
  imports: [EmptyStateComponent, ErrorStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="wrap">
      @if (error()) {
        <app-error-state message="The Week 6 run could not be loaded." retryLabel="Try again" (retry)="load()" />
      } @else if (!data()) {
        <div class="t1-skeleton sk"></div>
      } @else {
        @let d = data()!;
        <header class="head">
          <div>
            <h2>Week 6 evaluation: Docs pipeline</h2>
            <p class="muted">Run <code>{{ d.run.tag }}</code>, stored {{ d.run.updated_at }}. Every number below is computed from the stored rows.</p>
          </div>
        </header>

        <div class="tiles">
          <div class="tile"><span>Cases</span><strong>{{ d.n }}</strong></div>
          <div class="tile"><span>Failure modes</span><strong>{{ d.by_mode.length }}</strong></div>
          <div class="tile"><span>Deterministic checks</span><strong>{{ d.checks.length }}</strong></div>
          <div class="tile"><span>Regression cases</span><strong>{{ d.regressions.length }}</strong></div>
          <div class="tile"><span>Human labels</span><strong>{{ d.labelled }}</strong></div>
          @for (j of judgeRows(); track j.key) {
            <div class="tile"><span>{{ j.title }} agreement</span>
              <strong>{{ j.agreement }}</strong></div>
          }
        </div>

        <section class="card">
          <h3>Notes</h3>
          <textarea class="t1-input notes" rows="4" [value]="notes()" (input)="notes.set($any($event.target).value)"
                    aria-label="Notes about this run"></textarea>
          <div class="row"><button type="button" class="t1-btn" (click)="saveNotes()" [disabled]="notes() === d.run.notes">Save notes</button></div>
        </section>

        <section class="card">
          <h3>By failure mode</h3>
          <div class="table-wrap"><table class="tbl">
            <thead><tr><th>Mode</th><th class="num">Cases</th>
              @for (c of d.checks; track c) { <th class="num" [title]="c">{{ checkLabel(c) }}</th> }
              @for (j of judgeRows(); track j.key) { <th class="num">{{ j.title }} GOOD</th> }</tr></thead>
            <tbody>
              @for (m of d.by_mode; track m.mode) {
                <tr><td><strong>{{ m.label }}</strong><div class="muted small">{{ m.description }}</div></td>
                  <td class="num">{{ m.n }}</td>
                  @for (c of d.checks; track c) { <td class="num">{{ m.checks[c] }}/{{ m.n }}</td> }
                  @for (j of judgeRows(); track j.key) { <td class="num">{{ m.judge_good[j.key] ?? 0 }}/{{ m.n }}</td> }</tr>
              }
            </tbody>
          </table></div>
        </section>

        <section class="card">
          <h3>Judges against the human labels</h3>
          @for (j of judgeRows(); track j.key) {
            <p><strong>{{ j.title }}</strong> (rubric <code>{{ j.version }}</code>): GOOD {{ j.good }}, NOT_GOOD {{ j.notGood }};
              agreement with people {{ j.agreement }}.
              @if (j.disagreements.length) { Disagrees on {{ j.disagreements.join(', ') }}. }</p>
          }
          @for (p of promptKeys(); track p) {
            <details><summary>Rubric {{ p }}</summary><pre class="prompt">{{ d.prompts[p] }}</pre></details>
          }
        </section>

        <section class="card">
          <div class="row between">
            <h3>Cases</h3>
            <label class="filter">Mode
              <select class="t1-select" [value]="filter()" (change)="filter.set($any($event.target).value)">
                <option value="">All ({{ d.n }})</option>
                @for (m of d.by_mode; track m.mode) { <option [value]="m.mode">{{ m.short }} ({{ m.n }})</option> }
              </select>
            </label>
          </div>
          @if (!rows().length) { <app-empty-state title="No cases" detail="No case has this mode." /> }
          @else {
            <div class="table-wrap"><table class="tbl">
              <thead><tr><th>Case</th><th>Question</th><th>Mode</th><th>Expected</th><th>Checks</th>
                @for (j of judgeRows(); track j.key) { <th>{{ j.title }}</th> }<th>Human</th></tr></thead>
              <tbody>
                @for (r of rows(); track r.case_id) {
                  <tr [class.fail]="!r.passed">
                    <td><code>{{ r.case_id }}</code>@if (r.is_regression) { <span class="tag">regression</span> }
                      @if (r.regression_trace_id) { <div class="muted small">trace {{ r.regression_trace_id.slice(0, 8) }}</div> }</td>
                    <td>{{ r.question }}<details><summary class="small">Reply</summary><p class="reply">{{ r.reply }}</p></details></td>
                    <td>{{ modeLabel(r.mode) }}</td>
                    <td>{{ r.expected_behavior }}</td>
                    <td>{{ passCount(r) }}/{{ checkCount(r) }}</td>
                    @for (j of judgeRows(); track j.key) { <td [attr.data-v]="verdict(r, j.key)">{{ verdict(r, j.key) || '-' }}</td> }
                    <td [attr.data-v]="r.human_label">{{ r.human_label || '-' }}</td>
                  </tr>
                }
              </tbody>
            </table></div>
          }
        </section>
      }
    </div>
  `,
  styles: [`
    .wrap { display: flex; flex-direction: column; gap: 1rem; }
    .sk { height: 20rem; }
    .head h2 { margin: 0; font-size: 1.2rem; }
    .muted { color: var(--text-muted); } .small { font-size: .78rem; }
    .tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(10rem, 1fr)); gap: .6rem; }
    .tile { background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: .7rem .9rem; display: flex; flex-direction: column; gap: .2rem; }
    .tile span { font-size: .72rem; text-transform: uppercase; letter-spacing: .04em; color: var(--text-muted); }
    .tile strong { font-size: 1.15rem; }
    .card { background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 1rem 1.1rem; }
    .card h3 { margin: 0 0 .6rem; font-size: 1rem; }
    .notes { width: 100%; resize: vertical; }
    .row { display: flex; gap: .5rem; margin-top: .5rem; align-items: center; flex-wrap: wrap; } .between { justify-content: space-between; margin: 0 0 .6rem; }
    .filter { display: flex; gap: .4rem; align-items: center; font-size: .85rem; }
    .table-wrap { overflow-x: auto; }
    .tbl { width: 100%; border-collapse: collapse; font-size: .84rem; }
    .tbl th, .tbl td { text-align: left; padding: .45rem .6rem; border-bottom: 1px solid var(--border); vertical-align: top; }
    .tbl th { font-size: .7rem; text-transform: uppercase; letter-spacing: .04em; color: var(--text-muted); }
    .num { text-align: right; }
    tr.fail td:first-child { box-shadow: inset 3px 0 0 var(--danger); }
    [data-v='GOOD'] { color: var(--success); } [data-v='NOT_GOOD'] { color: var(--danger); }
    .tag { margin-left: .3rem; font-size: .68rem; padding: 0 .35rem; border-radius: var(--radius-sm); background: rgba(250,179,135,.15); color: var(--warning); }
    .prompt { white-space: pre-wrap; background: var(--surface-base); padding: .7rem; border-radius: var(--radius-md); font-size: .78rem; max-height: 24rem; overflow: auto; }
    .reply { white-space: pre-wrap; font-size: .8rem; color: var(--text-secondary); }
  `],
})
export class EvalComponent implements OnInit {
  private api = inject(CatalogService);
  private toast = inject(ToastService);
  data = signal<Week6 | null>(null);
  error = signal(false);
  filter = signal('');
  notes = signal('');

  rows = computed(() => (this.data()?.rows ?? []).filter(r => !this.filter() || r.mode === this.filter()));
  judgeRows = computed(() => Object.entries(this.data()?.judges ?? {}).map(([key, j]) => ({
    key, title: refLabel('judge_role', key), version: j.version ?? '-', good: j.good, notGood: j.not_good, disagreements: j.disagreements,
    agreement: j.agreement.n ? `${j.agreement.agree}/${j.agreement.n} = ${Math.round((j.agreement.agreement ?? 0) * 100)}%` : 'not measured',
  })));
  promptKeys = computed(() => Object.keys(this.data()?.prompts ?? {}));

  ngOnInit(): void { this.load(); }

  load(): void {
    this.error.set(false);
    this.api.week6().subscribe({ next: d => { this.data.set(d); this.notes.set(d.run.notes ?? ''); }, error: () => this.error.set(true) });
  }

  saveNotes(): void {
    const d = this.data();
    if (!d) return;
    this.api.saveRunNotes(d.run.tag, this.notes()).subscribe({
      next: () => { this.toast.success('Notes saved.'); this.load(); },
      error: () => this.toast.error('The notes were not saved.'),
    });
  }

  modeLabel(code: string): string { return refLabel('week6_failure_mode', code); }
  checkLabel(name: string): string { return name.split('_').join(' '); }
  verdict(r: Week6Row, key: string): string { return ((r as unknown as Record<string, { verdict?: string } | null>)[key]?.verdict) ?? ''; }
  checkCount(r: Week6Row): number { return Object.keys(r.checks ?? {}).length; }
  passCount(r: Week6Row): number { return Object.values(r.checks ?? {}).filter(Boolean).length; }
}
