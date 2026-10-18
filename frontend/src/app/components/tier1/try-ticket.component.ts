import { ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Subscription } from 'rxjs';
import { CustomerOption, Step, TicketAnswer, Tier1Service } from '../../services/tier1.service';
import { DecisionBannerComponent, ErrorStateComponent, PolicyBadgeComponent } from '../../shared/primitives';
import { EntitlementCardComponent } from '../../shared/entitlement-card.component';
import { StepTimelineComponent } from '../../shared/step-timeline.component';
import { SourceDrawerComponent } from '../../shared/source-drawer.component';
import { ToastService } from '../../shared/toast';
import { numberedSources } from './ticket-workspace.component';
import { groupByPolicy } from '../../shared/labels';
import { refValues } from '../../shared/ref-data';


/** Run the assistant on a pasted ticket or a random one. Nothing here changes a real ticket. */
@Component({
  selector: 'app-try-ticket',
  standalone: true,
  imports: [DecisionBannerComponent, EntitlementCardComponent, StepTimelineComponent, SourceDrawerComponent, ErrorStateComponent, PolicyBadgeComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="t1-page">
      <div class="t1-page__head">
        <div>
          <h1 class="t1-h1">Try a ticket</h1>
          <p class="t1-sub">See what the assistant does with a ticket, including the ones it should refuse to answer. Nothing here is saved to a real ticket.</p>
        </div>
      </div>

      <div class="cols">
        <section class="card" aria-labelledby="rand-h">
          <h2 id="rand-h">Draw a random ticket</h2>
          <p class="help">Picks one of the {{ sampleCount() ?? 'sample' }} sample tickets at random, not one chosen to look good. The seed is shown so the same draw can be repeated.</p>
          <button type="button" class="t1-btn t1-btn--primary" [disabled]="drawing()" (click)="randomTicket()">
            {{ drawing() ? 'Drawing' : 'Draw a random ticket and run it' }}</button>
        </section>

        <section class="card" aria-labelledby="own-h">
          <h2 id="own-h">Write your own</h2>
          @if (customersError()) {
            <app-error-state message="The customer list could not be loaded." retryLabel="Try again" (retry)="loadCustomers()" />
          } @else {
            <div class="row">
              <div class="field">
                <label class="t1-label" for="cust">Customer</label>
                <select id="cust" class="t1-select" [value]="customerId()" (change)="pickCustomer($any($event.target).value)">
                  <option value="">Choose a customer</option>
                  @for (g of groups(); track g.code) {
                    <optgroup [label]="g.label">
                      @for (c of g.items; track c.customer_id) { <option [value]="c.customer_id">{{ c.customer_id }}  {{ c.region }}, {{ c.plan }}</option> }
                    </optgroup>
                  }
                </select>
              </div>
              <div class="field">
                <label class="t1-label" for="ord">Order (optional)</label>
                <select id="ord" class="t1-select" [disabled]="!selected()" [value]="orderId()" (change)="orderId.set($any($event.target).value)">
                  <option value="">No order</option>
                  @for (o of selected()?.orders ?? []; track o.order_id) { <option [value]="o.order_id">{{ o.order_id }}  {{ o.age_days }} days old</option> }
                </select>
              </div>
            </div>
            @if (selected(); as c) { <p class="who">This customer is on the <app-policy-badge [version]="c.policy_version" />.</p> }

            <label class="t1-label" for="subj">Subject</label>
            <input id="subj" class="t1-input full" [value]="subject()" (input)="subject.set($any($event.target).value)" maxlength="300" />
            <label class="t1-label lbl" for="text">What the customer wrote</label>
            <textarea id="text" class="t1-textarea" rows="5" maxlength="4000" [value]="text()" (input)="text.set($any($event.target).value)"
                      placeholder="Paste or type a ticket"></textarea>

            <div class="examples" role="group" aria-label="Example tickets">
              <span class="help">Examples:</span>
              @for (e of examples; track e.label) {
                <button type="button" class="chipbtn" (click)="useExample(e)">{{ e.label }}</button>
              }
            </div>
            <button type="button" class="t1-btn t1-btn--primary" [disabled]="!canRun()" (click)="run()">
              {{ running() ? 'Working' : 'Run the assistant' }}</button>
          }
        </section>
      </div>

      @if (running() || result() || jobError()) {
        <div class="out" aria-live="polite">
          <section class="card">
            <h2>Result</h2>
            @if (running()) { <p class="working"><span class="spinner" aria-hidden="true"></span> The assistant is working</p> }
            @if (jobError()) { <app-error-state title="The assistant could not finish" [message]="jobError()!" retryLabel="Run again" (retry)="run()" /> }
            @if (result(); as r) {
              <app-decision-banner [result]="r" />
              @if (r.decision === 'ANSWER') {
                <pre class="reply">{{ r.customer_reply || r.reply }}</pre>
                <div class="sources">
                  @for (s of sources(); track s.n) {
                    <button type="button" class="chipbtn" (click)="openSource(s.slug)">[{{ s.n }}] {{ s.slug }}</button>
                  }
                  <button type="button" class="t1-btn t1-btn--ghost" (click)="copy(r.customer_reply || r.reply)">Copy reply</button>
                </div>
              } @else if (r.draft) {
                <details><summary>The draft the assistant blocked</summary><pre class="reply">{{ r.draft }}</pre></details>
              }
              <p class="help">Trace <code>{{ r.trace_id }}</code>, {{ (r.latency_ms / 1000).toFixed(1) }} s, {{ r.total_tokens }} tokens.</p>
            }
          </section>
          <section class="side">
            <app-entitlement-card [entitlement]="result()?.entitlement ?? null" [answered]="result()?.decision === 'ANSWER'" [ran]="!!result()" />
            <article class="card"><h2>How I got here</h2><app-step-timeline [steps]="steps()" [running]="running()" /></article>
          </section>
        </div>
      }
    </div>
    @if (drawer(); as d) { <app-source-drawer [slug]="d.slug" [chunkText]="d.text" (closed)="drawer.set(null)" /> }
  `,
  styles: [`
    .cols { display: grid; grid-template-columns: minmax(0, 22rem) minmax(0, 1fr); gap: 1rem; align-items: start; }
    @media (max-width: 900px) { .cols, .out { grid-template-columns: 1fr !important; } }
    .card { background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 1rem 1.1rem; }
    h2 { font-size: .78rem; text-transform: uppercase; letter-spacing: .05em; color: var(--text-muted); margin-bottom: .6rem; }
    .help { font-size: .8rem; color: var(--text-muted); margin: 0 0 .75rem; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: .75rem; margin-bottom: .6rem; }
    .field { min-width: 0; } .field select { width: 100%; }
    .who { font-size: .82rem; color: var(--text-secondary); margin: 0 0 .8rem; display: flex; gap: .4rem; align-items: center; flex-wrap: wrap; }
    .full { width: 100%; } .lbl { margin-top: .7rem; }
    .examples { display: flex; flex-wrap: wrap; gap: .4rem; align-items: center; margin: .7rem 0; }
    .chipbtn { background: var(--surface-base); border: 1px solid var(--border-strong); color: var(--text-secondary); border-radius: 999px; padding: .2rem .65rem; font: inherit; font-size: .78rem; cursor: pointer; }
    .chipbtn:hover { border-color: var(--accent); color: var(--text-primary); }
    .out { display: grid; grid-template-columns: minmax(0, 1fr) minmax(15rem, 22rem); gap: 1rem; margin-top: 1rem; align-items: start; }
    .side { display: flex; flex-direction: column; gap: .9rem; }
    .reply { white-space: pre-wrap; font-family: var(--font-sans); font-size: .93rem; line-height: 1.6; background: var(--surface-base); padding: .9rem 1rem; border-radius: var(--radius-md); margin: .8rem 0; }
    .sources { display: flex; flex-wrap: wrap; gap: .4rem; align-items: center; }
    .working { display: flex; gap: .6rem; align-items: center; font-size: .9rem; }
    details summary { cursor: pointer; margin-top: .8rem; color: var(--accent); font-size: .85rem; }
  `],
})
export class TryTicketComponent implements OnInit {
  private api = inject(Tier1Service);
  private router = inject(Router);
  private toast = inject(ToastService);
  private destroyRef = inject(DestroyRef);

  get examples() { return refValues('example_ticket').map(v => ({ label: v.label, subject: String(v.meta['subject'] ?? ''), text: String(v.meta['body'] ?? '') })); }
  sampleCount = signal<number | null>(null);
  customers = signal<CustomerOption[]>([]);
  customersError = signal(false);
  customerId = signal('');
  orderId = signal('');
  subject = signal('');
  text = signal('');
  drawing = signal(false);
  running = signal(false);
  jobError = signal<string | null>(null);
  steps = signal<Step[]>([]);
  result = signal<TicketAnswer | null>(null);
  drawer = signal<{ slug: string; text: string } | null>(null);
  private job?: Subscription;

  groups = computed(() => groupByPolicy(this.customers()));
  selected = computed(() => this.customers().find(c => c.customer_id === this.customerId()) ?? null);
  sources = computed(() => { const r = this.result(); return r ? numberedSources(r.customer_reply, r.citations) : []; });
  canRun = computed(() => !!this.customerId() && this.text().trim().length > 3 && !this.running());

  ngOnInit(): void {
    this.loadCustomers();
    this.api.tickets({}).subscribe({ next: q => this.sampleCount.set(q.total), error: () => undefined });
    this.destroyRef.onDestroy(() => this.job?.unsubscribe());
  }

  loadCustomers(): void {
    this.customersError.set(false);
    this.api.customers().subscribe({ next: c => this.customers.set(c), error: () => this.customersError.set(true) });
  }

  pickCustomer(id: string): void { this.customerId.set(id); this.orderId.set(''); }
  useExample(e: { subject: string; text: string }): void { this.subject.set(e.subject); this.text.set(e.text); }

  randomTicket(): void {
    this.drawing.set(true);
    this.api.randomTicket().subscribe({
      next: r => this.router.navigate(['/tickets', r.ticket_id], { queryParams: { run: 1, seed: r.seed } }),
      error: () => { this.drawing.set(false); this.toast.error('Could not draw a ticket.'); },
    });
  }

  run(): void {
    this.job?.unsubscribe();
    this.running.set(true); this.jobError.set(null); this.steps.set([]); this.result.set(null);
    this.api.answer({ text: this.text(), subject: this.subject(), customer_id: this.customerId(), order_id: this.orderId() || undefined })
      .subscribe({
        next: ({ job_id }) => {
          this.job = this.api.pollJob(job_id).subscribe({
            next: j => {
              this.steps.set(j.steps);
              if (j.status === 'done' && j.result) { this.result.set(j.result); this.running.set(false); }
              if (j.status === 'error') { this.jobError.set(j.error ?? 'The assistant could not finish.'); this.running.set(false); }
            },
            error: () => { this.jobError.set('Lost contact with the server.'); this.running.set(false); },
          });
        },
        error: err => {
          this.running.set(false);
          this.jobError.set(err.status === 429 ? 'The assistant is busy. Try again in a minute.' : 'The assistant could not be started.');
        },
      });
  }

  openSource(slug: string): void {
    this.drawer.set({ slug, text: this.result()?.sources.find(s => s.slug === slug)?.text ?? '' });
  }
  copy(text: string): void { navigator.clipboard?.writeText(text).then(() => this.toast.success('Reply copied.')); }
}
