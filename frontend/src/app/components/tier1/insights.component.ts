import { ConfirmService } from '../../shared/confirm';
import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { EvalRun, FeedbackItem, Metrics, Tier1Service } from '../../services/tier1.service';
import { EmptyStateComponent, ErrorStateComponent, KpiTileComponent } from '../../shared/primitives';
import { ToastService } from '../../shared/toast';
import { feedbackReasons, pct, usd } from '../../shared/labels';

type Tab = 'overview' | 'inbox' | 'eval';

/**
 * For the team lead. Rule for this page: a number that was not measured says "Not measured",
 * never zero and never a guess; and deflection is always shown next to the re-open rate.
 */
@Component({
  selector: 'app-insights',
  standalone: true,
  imports: [RouterLink, DatePipe, KpiTileComponent, EmptyStateComponent, ErrorStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="t1-page">
      <div class="t1-page__head">
        <div>
          <h1 class="t1-h1">Tier-1 insights</h1>
          <p class="t1-sub">How the assistant is doing, where it fails, and how a failure becomes a permanent test.</p>
        </div>
        <button type="button" class="t1-btn" (click)="refresh()">Refresh</button>
      </div>

      <div class="tabs" role="tablist" aria-label="Sections">
        <button type="button" role="tab" [attr.aria-selected]="tab() === 'overview'" (click)="tab.set('overview')">Overview</button>
        <button type="button" role="tab" [attr.aria-selected]="tab() === 'inbox'" (click)="tab.set('inbox'); loadInbox()">
          Review inbox @if (openCount()) { <span class="badge">{{ openCount() }}</span> }</button>
        <button type="button" role="tab" [attr.aria-selected]="tab() === 'eval'" (click)="tab.set('eval')">Evaluation</button>
      </div>

      @if (tab() === 'overview') {
        @if (metrics(); as m) {
          <h2 class="section">Quality (last evaluation run{{ m.eval ? ', ' + m.eval.n + ' cases' : '' }})</h2>
          @if (m.eval; as e) {
            <div class="tiles">
              <app-kpi-tile label="Passed all checks" [value]="pct(e.pass_rate)" hint="Every assertion on every case" />
              <app-kpi-tile label="Wrong policy cited" [value]="pct(e.superseded_final_rate)"
                [hint]="e.superseded_before === null ? 'No before-run to compare with' : 'Before the version filter and guard: ' + pct(e.superseded_before)"
                [tone]="e.superseded_final_rate === 0 ? 'good' : 'bad'" />
              <app-kpi-tile label="Both policy versions live" [value]="e.both_versions.passed + ' of ' + e.both_versions.n"
                [hint]="e.both_versions.pairs_both_correct + ' of ' + e.both_versions.pairs + ' question pairs right for both customers'" />
              <app-kpi-tile label="Judge agrees with a human" [value]="pct(e.judge_agreement)"
                [hint]="e.judge_labels ? e.judge_labels + ' human labels (target ' + pct(m.agreement_target) + ')' : 'Needs human labels'"
                [tone]="e.judge_agreement === null ? '' : e.judge_agreement >= m.agreement_target ? 'good' : 'bad'" />
              <app-kpi-tile label="Cost per deflected ticket" [value]="usd(e.cost_per_deflected_usd)" hint="All spend, escalations included" />
            </div>
          } @else {
            <app-empty-state title="No evaluation run yet" detail="Run the evaluation suite to fill this section." />
          }

          <h2 class="section">Deflection and re-open, together</h2>
          <div class="tiles tiles--two">
            <app-kpi-tile label="Deflected" [value]="pct(m.second_contact?.deflection_rate ?? null)" hint="Answered without a person" />
            <app-kpi-tile label="Simulated re-open" [value]="pct(m.second_contact?.simulated_reopen_rate ?? null)"
              [hint]="m.second_contact ? 'Follow-up written for ' + m.second_contact.n + ' deflected tickets' : 'Run the second-contact evaluation'"
              [tone]="m.second_contact ? 'warn' : ''" />
          </div>

          <h2 class="section">Live traffic ({{ m.tickets_processed }} tickets processed)</h2>
          <div class="tiles">
            <app-kpi-tile label="Assistant answered" [value]="pct(m.ai_answer_rate)" />
            <app-kpi-tile label="Assistant escalated" [value]="pct(m.ai_escalation_rate)" />
            <app-kpi-tile label="Agents edited the draft" [value]="pct(m.edit_rate)" hint="Of approved drafts" />
            <app-kpi-tile label="Cost per answered ticket" [value]="usd(m.cost_per_answered_usd)" />
            <app-kpi-tile label="Time to draft" [value]="m.latency_p50_s === null ? 'Not measured' : m.latency_p50_s + ' s'"
              [hint]="m.latency_p95_s === null ? '' : 'p95 ' + m.latency_p95_s + ' s'" />
          </div>

          <h2 class="section">Where it fails</h2>
          @if (m.eval?.failure_modes?.length) {
            <div class="table-wrap">
              <table class="table" aria-label="Failure modes">
                <thead><tr><th>Mode</th><th>Severity</th><th class="num">Cases</th><th>Example</th></tr></thead>
                <tbody>
                  @for (f of m.eval!.failure_modes; track f.mode) {
                    <tr><td>{{ modeName(f.mode) }}</td><td><span class="sev" [attr.data-sev]="f.severity">{{ f.severity }}</span></td>
                      <td class="num">{{ f.count }}</td><td><a [routerLink]="['/trace', f.trace_id]">Read the trace</a></td></tr>
                  }
                </tbody>
              </table>
            </div>
          } @else {
            <app-empty-state title="No failures recorded" detail="Either the last run passed everything, or no run exists yet. A suite that never fails is a reason to add harder cases." />
          }

          @if (m.per_day.length) {
            <h2 class="section">Last days</h2>
            <ul class="days" aria-label="Tickets per day">
              @for (d of m.per_day; track d.day) {
                <li><span class="day">{{ d.day }}</span>
                  <span class="bar" [style.width.%]="barWidth(d.n, m)"><span class="bar__a" [style.flex]="d.answered"></span><span class="bar__e" [style.flex]="d.escalated"></span></span>
                  <span class="n">{{ d.answered }} answered, {{ d.escalated }} escalated</span></li>
              }
            </ul>
          }
        } @else if (error()) {
          <app-error-state message="The numbers could not be loaded." retryLabel="Try again" (retry)="loadMetrics()" />
        } @else {
          <div class="tiles"><div class="t1-skeleton sk"></div><div class="t1-skeleton sk"></div><div class="t1-skeleton sk"></div></div>
        }
      }

      @if (tab() === 'inbox') {
        <p class="intro">Answers agents marked wrong. Turn a report into a permanent test: it joins every future evaluation run, so the failure stays guarded after it is fixed.</p>
        @if (inboxError()) {
          <app-error-state message="The inbox could not be loaded." retryLabel="Try again" (retry)="loadInbox()" />
        } @else if (!inbox().length) {
          <app-empty-state title="Inbox is empty" detail="Reports appear here when an agent uses Report wrong answer on a draft." />
        } @else {
          <ul class="list">
            @for (f of inbox(); track f.id) {
              <li class="item">
                <div class="item__top">
                  <strong>{{ reasonText(f.reason) }}</strong>
                  <span class="muted">{{ f.created_at | date: 'MMM d, HH:mm' }} by {{ f.user_email }}</span>
                </div>
                @if (f.comment) { <p class="comment">{{ f.comment }}</p> }
                <div class="item__foot">
                  @if (f.ticket_id) { <a [routerLink]="['/tickets', f.ticket_id]">Ticket {{ f.ticket_id }}</a> }
                  <a [routerLink]="['/trace', f.trace_id]">Trace</a>
                  <span class="grow"></span>
                  @if (f.status === 'case_created') {
                    <span class="done">Test {{ f.eval_case_id }} added</span>
                    <button type="button" class="t1-btn" [disabled]="running()" (click)="runCase(f.eval_case_id!)">Run this test</button>
                  }
                  @else { <button type="button" class="t1-btn t1-btn--primary" [disabled]="!f.ticket_id || creating() === f.id" (click)="createCase(f)">
                    {{ creating() === f.id ? 'Creating' : 'Create evaluation case' }}</button> }
                </div>
              </li>
            }
          </ul>
        }
      }

      @if (tab() === 'eval') {
        <p class="intro">Run the integrated suite from here. The regression cases (every failure you turned into a test) run in seconds when their answers are cached; the full suite takes 20 to 30 minutes on the free tier.</p>
        <div class="runbar">
          <button type="button" class="t1-btn t1-btn--primary" [disabled]="running()" (click)="startRun('regression')">Run regression cases</button>
          <button type="button" class="t1-btn" [disabled]="running()" (click)="startRun(null)">Run the full suite</button>
        </div>
        @if (run(); as r) {
          <section class="card" aria-live="polite">
            <h2>Run {{ r.run_id }}</h2>
            <p class="state" [attr.data-state]="r.status">
              @if (r.status === 'running') { <span class="spinner" aria-hidden="true"></span> Running }
              @else if (r.status === 'failed') { The run stopped before finishing. If the log mentions a usage cap, the free tier's daily limit was reached: try again tomorrow. }
              @else if (r.summary) { <strong [attr.data-ok]="r.summary.passed === r.summary.n">{{ r.summary.passed === r.summary.n ? 'Green' : 'Red' }}</strong>:
                {{ r.summary.passed }} of {{ r.summary.n }} cases passed. }
            </p>
            @if (r.summary && r.summary.failure_modes.length) { <p class="muted">Failure modes: {{ r.summary.failure_modes.join(', ') }}</p> }
            @if (r.cases?.length) {
              @for (c of r.cases; track c.case_id) {
                <div class="case">
                  <p><strong>{{ c.case_id }}</strong> <span [attr.data-ok]="c.passed">{{ c.passed ? 'passes' : 'fails' }}</span>
                    (decision {{ c.decision }}) <a [routerLink]="['/trace', c.trace_id]">Open trace</a></p>
                  <ul class="checks">
                    @for (k of checkNames(c.checks); track k) {
                      <li [attr.data-ok]="c.checks[k]">{{ c.checks[k] ? 'Pass' : 'Fail' }}: {{ modeName(k) }}</li>
                    }
                  </ul>
                </div>
              }
            }
            <details class="log-wrap" [open]="r.status === 'running'">
              <summary>Run log</summary>
              <pre class="log">{{ r.log_tail.join('\\n') || 'Waiting for the first case' }}</pre>
            </details>
          </section>
        }
      }
    </div>
  `,
  styles: [`
    .tabs { display: flex; gap: .35rem; margin-bottom: 1rem; flex-wrap: wrap; }
    .tabs button { background: var(--surface-card); border: 1px solid var(--border); color: var(--text-secondary); border-radius: 999px; padding: .4rem .9rem; font: inherit; font-size: .84rem; font-weight: 600; cursor: pointer; }
    .tabs button[aria-selected='true'] { background: var(--accent); border-color: var(--accent); color: #fff; }
    .badge { margin-left: .3rem; background: var(--danger); color: #fff; border-radius: 999px; padding: 0 .4rem; font-size: .7rem; }
    .section { font-size: .78rem; text-transform: uppercase; letter-spacing: .05em; color: var(--text-muted); margin: 1.4rem 0 .6rem; }
    .tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(11.5rem, 1fr)); gap: .75rem; }
    .tiles--two { grid-template-columns: repeat(2, minmax(11.5rem, 16rem)); }
    .sk { height: 5.5rem; }
    .table-wrap { background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-lg); overflow-x: auto; }
    .table { width: 100%; border-collapse: collapse; font-size: .88rem; }
    th { text-align: left; font-size: .72rem; text-transform: uppercase; letter-spacing: .05em; color: var(--text-muted); padding: .65rem .9rem; border-bottom: 1px solid var(--border); }
    td { padding: .65rem .9rem; border-bottom: 1px solid var(--border); } tr:last-child td { border-bottom: 0; } .num { text-align: right; }
    .sev { padding: .1rem .5rem; border-radius: var(--radius-sm); font-size: .72rem; font-weight: 700; text-transform: uppercase; background: rgba(108,112,134,.2); }
    .sev[data-sev='critical'] { background: rgba(243,139,168,.18); color: var(--danger); } .sev[data-sev='high'] { background: rgba(250,179,135,.18); color: var(--warning); }
    .days { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: .35rem; font-size: .82rem; }
    .days li { display: grid; grid-template-columns: 6.5rem 1fr 12rem; gap: .6rem; align-items: center; }
    .day, .n { color: var(--text-muted); } .bar { display: flex; height: .7rem; border-radius: 4px; overflow: hidden; min-width: 2px; }
    .bar__a { background: var(--success); } .bar__e { background: var(--warning); }
    .intro { color: var(--text-secondary); font-size: .9rem; margin-bottom: 1rem; max-width: 46rem; }
    .list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: .7rem; }
    .item { background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: .85rem 1rem; }
    .item__top { display: flex; flex-wrap: wrap; gap: .4rem .8rem; align-items: baseline; } .muted { color: var(--text-muted); font-size: .8rem; }
    .comment { margin: .4rem 0; font-size: .9rem; color: var(--text-secondary); }
    .item__foot { display: flex; flex-wrap: wrap; gap: .8rem; align-items: center; margin-top: .6rem; font-size: .84rem; } .grow { flex: 1; }
    .done { color: var(--success); font-weight: 600; }
    .runbar { display: flex; gap: .6rem; flex-wrap: wrap; margin-bottom: 1rem; }
    .card { background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 1rem 1.1rem; }
    .card h2 { font-size: .78rem; text-transform: uppercase; letter-spacing: .05em; color: var(--text-muted); margin-bottom: .5rem; }
    .state { display: flex; gap: .5rem; align-items: center; margin: 0 0 .5rem; } [data-ok='true'] { color: var(--success); } [data-ok='false'] { color: var(--danger); }
    .case { margin-top: .6rem; } .checks { list-style: none; padding: 0; margin: .3rem 0 0; display: grid; gap: .2rem; font-size: .84rem; }
    .log { background: var(--surface-base); padding: .7rem; border-radius: var(--radius-md); font-size: .78rem; overflow-x: auto; white-space: pre-wrap; margin: .5rem 0 0; }
  `],
})
export class InsightsComponent implements OnInit {
  private readonly confirm = inject(ConfirmService);
  private api = inject(Tier1Service);
  private toast = inject(ToastService);
  private destroyRef = inject(DestroyRef);

  pct = pct; usd = usd;
  tab = signal<Tab>('overview');
  metrics = signal<Metrics | null>(null);
  error = signal(false);
  inbox = signal<FeedbackItem[]>([]);
  inboxError = signal(false);
  creating = signal<number | null>(null);
  run = signal<EvalRun | null>(null);
  running = signal(false);
  private pollTimer?: ReturnType<typeof setTimeout>;

  ngOnInit(): void {
    this.loadMetrics();
    this.loadInbox();
    this.destroyRef.onDestroy(() => clearTimeout(this.pollTimer));
  }

  refresh(): void { this.loadMetrics(); this.loadInbox(); }
  loadMetrics(): void {
    this.error.set(false);
    this.api.metrics().subscribe({ next: m => this.metrics.set(m), error: () => this.error.set(true) });
  }
  loadInbox(): void {
    this.inboxError.set(false);
    this.api.feedbackInbox().subscribe({ next: f => this.inbox.set(f), error: () => this.inboxError.set(true) });
  }
  openCount(): number { return this.inbox().filter(f => f.status === 'open').length; }
  modeName(mode: string): string { return mode.split('_').join(' '); }
  reasonText(v: string): string { return feedbackReasons().find(r => r.value === v)?.label ?? v; }
  barWidth(n: number, m: Metrics): number { return Math.max(4, (n / Math.max(...m.per_day.map(d => d.n), 1)) * 100); }

  createCase(f: FeedbackItem): void {
    this.creating.set(f.id);
    this.api.feedbackToCase(f.id).subscribe({
      next: r => { this.creating.set(null); this.toast.success(`Test ${r.case_id} added. It runs in every evaluation from now on.`); this.loadInbox(); },
      error: err => { this.creating.set(null); this.toast.error(err.status === 409 ? 'This failure already has a test.' : 'Could not create the test.'); },
    });
  }

  async startRun(only: string | null): Promise<void> {
    if (!only && !(await this.confirm.ask('The full suite takes 20 to 30 minutes and uses model quota. Start it?'))) return;
    this.running.set(true);
    this.api.evalRun(only).subscribe({
      next: ({ run_id }) => this.poll(run_id),
      error: err => { this.running.set(false); this.toast.error(err.status === 409 ? 'A run is already in progress.' : 'The run could not be started.'); },
    });
  }

  runCase(caseId: string): void {
    this.tab.set('eval');
    this.running.set(true);
    this.api.runRegressionCase(caseId).subscribe({
      next: ({ run_id }) => this.poll(run_id),
      error: err => { this.running.set(false); this.toast.error(err.status === 409 ? 'A run is already in progress.' : 'The test could not be started.'); },
    });
  }

  checkNames(checks: Record<string, boolean>): string[] {
    return Object.keys(checks).sort((a, b) => Number(checks[a]) - Number(checks[b]));   // failures first
  }

  private poll(runId: string): void {
    this.api.evalStatus(runId).subscribe({
      next: r => {
        this.run.set(r);
        if (r.status === 'running') this.pollTimer = setTimeout(() => this.poll(runId), 4000);
        else { this.running.set(false); this.loadMetrics(); }
      },
      error: () => { this.running.set(false); this.toast.error('Lost track of the run.'); },
    });
  }
}
