import { ChangeDetectionStrategy, Component, DestroyRef, ElementRef, HostListener, ViewChild, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import { AuthService } from '../../services/auth.service';
import { Citation, Step, TicketAnswer, TicketDetail, Tier1Service } from '../../services/tier1.service';
import { DecisionBannerComponent, EmptyStateComponent, ErrorStateComponent, PolicyBadgeComponent } from '../../shared/primitives';
import { EntitlementCardComponent } from '../../shared/entitlement-card.component';
import { StepTimelineComponent } from '../../shared/step-timeline.component';
import { SourceDrawerComponent } from '../../shared/source-drawer.component';
import { ModalComponent } from '../../shared/modal.component';
import { ToastService } from '../../shared/toast';
import { feedbackReasons, reasonLabel, usd } from '../../shared/labels';
import { refLabel } from '../../shared/ref-data';

/** Footer lines of the customer text look like "[1] refund-policy-30d (30-day refund policy)". */
export function numberedSources(text: string, citations: Citation[]): { n: number; slug: string; citation: Citation | undefined }[] {
  const out: { n: number; slug: string; citation: Citation | undefined }[] = [];
  for (const m of text.matchAll(/^\[(\d+)\]\s+([a-z0-9-]+)/gm)) {
    out.push({ n: Number(m[1]), slug: m[2], citation: citations.find(c => c.slug === m[2]) });
  }
  return out;
}


@Component({
  selector: 'app-ticket-workspace',
  standalone: true,
  imports: [RouterLink, PolicyBadgeComponent, DecisionBannerComponent, EmptyStateComponent,
            ErrorStateComponent, EntitlementCardComponent, StepTimelineComponent, SourceDrawerComponent, ModalComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="t1-page ws">
      <nav class="crumbs" aria-label="Breadcrumb"><a routerLink="/tickets">Tickets</a> / <span>{{ id }}</span></nav>

      @if (loadError()) {
        <app-error-state message="This ticket could not be loaded." retryLabel="Try again" (retry)="load()">
          <a class="t1-btn" routerLink="/tickets">Back to tickets</a>
        </app-error-state>
      } @else if (!detail()) {
        <div class="t1-skeleton sk-head"></div><div class="t1-skeleton sk-body"></div>
      } @else {
        @if (seed() !== null) {
          <p class="seed" role="note">Random draw, seed <code>{{ seed() }}</code>. Open <code>/tickets/{{ id }}</code> to return to this exact ticket.</p>
        }

        <div class="tabs" role="tablist" aria-label="Sections">
          <button type="button" role="tab" [attr.aria-selected]="tab() === 'ticket'" (click)="tab.set('ticket')">Ticket</button>
          <button type="button" role="tab" [attr.aria-selected]="tab() === 'draft'" (click)="tab.set('draft')">Draft</button>
          <button type="button" role="tab" [attr.aria-selected]="tab() === 'steps'" (click)="tab.set('steps')">How I got here</button>
        </div>

        <div class="grid">
          <!-- LEFT: the ticket and what the account system says -->
          <section class="pane" [class.pane--active]="tab() === 'ticket'" aria-label="Ticket and customer">
            <article class="card">
              <h1 class="subject">{{ detail()!.subject || 'Support request' }}</h1>
              <p class="body">{{ detail()!.body }}</p>
            </article>
            <article class="card people">
              <h2>Customer</h2>
              <dl>
                <div><dt>Name</dt><dd>{{ detail()!.customer.name }}</dd></div>
                <div><dt>Email</dt><dd>{{ detail()!.customer.email }}</dd></div>
                <div><dt>Region</dt><dd>{{ detail()!.customer.region }}</dd></div>
                <div><dt>Plan</dt><dd>{{ detail()!.customer.plan }}</dd></div>
              </dl>
              <h2>Order</h2>
              <dl>
                <div><dt>Order</dt><dd>{{ detail()!.order.order_id }}</dd></div>
                <div><dt>Placed</dt><dd>{{ detail()!.order.purchase_date }} ({{ detail()!.order.age_days }} days ago)</dd></div>
                <div><dt>Amount</dt><dd>{{ detail()!.order.amount }} {{ detail()!.order.currency }}</dd></div>
                <div><dt>Status</dt><dd>{{ detail()!.order.status }}</dd></div>
              </dl>
            </article>
            <app-entitlement-card [entitlement]="result()?.entitlement ?? null" [answered]="result()?.decision === 'ANSWER'" [ran]="!!result()" />
          </section>

          <!-- CENTRE: the draft and the decision -->
          <section class="pane pane--centre" [class.pane--active]="tab() === 'draft'" aria-label="Draft reply">
            @if (lastDecision(); as d) {
              <p class="decided" role="status">
                Last decision: <strong>{{ decisionWord(d.action) }}</strong> by {{ d.user_email }}
                @if (d.edit_ratio !== null && d.edit_ratio > 0) { (edited, {{ (d.edit_ratio * 100).toFixed(0) }}% changed) }
              </p>
            }

            @if (running()) {
              <div class="working" role="status" aria-live="polite">
                <span class="spinner" aria-hidden="true"></span> The assistant is working on this ticket. You can read the ticket while you wait.
                <button type="button" class="t1-btn t1-btn--ghost" (click)="cancel()">Stop</button>
              </div>
              <div class="t1-skeleton sk-draft"></div>
            } @else if (jobError()) {
              <app-error-state title="The assistant could not finish" [message]="jobError()!" [traceId]="traceId()" retryLabel="Run again" (retry)="run()">
                <button type="button" class="t1-btn t1-btn--danger" (click)="openEscalate()">Escalate to a person</button>
              </app-error-state>
            } @else {
              @if (result(); as r) {
              <app-decision-banner [result]="r" />

              @if (r.decision === 'ANSWER') {
                <label class="t1-label" for="draft">Reply to the customer
                  @if (dirty()) { <span class="edited">Edited</span> }</label>
                <textarea #editor id="draft" class="t1-textarea draft" rows="11" [value]="draft()"
                          (input)="draft.set($any($event.target).value)" aria-describedby="draft-help"></textarea>
                <p id="draft-help" class="help">Numbered markers like [1] point to the sources below. Edit freely; your edits are recorded.</p>

                @if (sources().length) {
                  <div class="sources" aria-label="Sources used">
                    <span class="sources__label">Sources</span>
                    @for (s of sources(); track s.n) {
                      <button type="button" class="source" (click)="openSource(s.slug)" [attr.aria-label]="'Open source ' + s.n + ': ' + s.slug">
                        <span class="source__n">[{{ s.n }}]</span> {{ s.slug }}
                        @if (s.citation && s.citation.policy_version !== 'none') { <app-policy-badge [version]="s.citation.policy_version" /> }
                      </button>
                    }
                  </div>
                }
                @if (needsEntitlement()) {
                  <p class="block" role="alert">This draft talks about refunds or delivery, but the customer's entitlement was never checked. Approve is disabled; escalate or run the assistant again.</p>
                }
              } @else {
                <div class="card esc">
                  <h2>Why it did not answer</h2>
                  <p>{{ why(r.reason) }}</p>
                  @for (v of r.violations; track v.code) { <p class="viol"><code>{{ v.code }}</code> {{ v.detail }}</p> }
                  @if (r.draft) {
                    <details><summary>Show the draft the assistant blocked</summary><pre class="blocked">{{ r.draft }}</pre></details>
                  }
                </div>
              }

              <div class="actions" role="group" aria-label="Decision">
                @if (r.decision === 'ANSWER') {
                  <button type="button" class="t1-btn t1-btn--primary" [disabled]="!canApprove()" (click)="approve()">
                    {{ busy() ? 'Saving' : 'Approve and copy' }} <span class="t1-kbd kbd-on">Ctrl+Enter</span></button>
                  <button type="button" class="t1-btn" (click)="focusEditor()">Edit <span class="t1-kbd">E</span></button>
                }
                <button type="button" class="t1-btn" (click)="regenerate()">Run again <span class="t1-kbd">R</span></button>
                <button type="button" class="t1-btn t1-btn--danger" (click)="openEscalate()">Escalate <span class="t1-kbd">Shift+E</span></button>
                <button type="button" class="t1-btn t1-btn--ghost" (click)="feedbackOpen.set(true)">Report wrong answer</button>
              </div>
              } @else {
              <app-empty-state title="No draft yet" detail="The assistant has not looked at this ticket. It checks the customer's entitlement and searches the help centre, then drafts a reply for you to review.">
                <button type="button" class="t1-btn t1-btn--primary" (click)="run()">Run the assistant <span class="t1-kbd kbd-on">R</span></button>
              </app-empty-state>
              }
            }
          </section>

          <!-- RIGHT: how it got there -->
          <section class="pane" [class.pane--active]="tab() === 'steps'" aria-label="How I got here">
            <article class="card">
              <h2>How I got here</h2>
              <app-step-timeline [steps]="steps()" [running]="running()" />
              @if (!steps().length && !running() && result()) {
                <p class="help">Steps are shown live while the assistant runs. This draft was produced in an earlier run.</p>
              }
            </article>
            @if (result(); as r) {
              <article class="card facts">
                <dl>
                  <div><dt>Trace</dt><dd><code>{{ r.trace_id }}</code>
                    <button type="button" class="link" (click)="copyTrace(r.trace_id)">Copy</button></dd></div>
                  <div><dt>Time</dt><dd>{{ (r.latency_ms / 1000).toFixed(1) }} s</dd></div>
                  <div><dt>Tokens</dt><dd>{{ r.total_tokens }}</dd></div>
                  <div><dt>Cost</dt><dd>{{ cost(r.cost_usd) }}</dd></div>
                </dl>
                @if (auth.isAdmin) { <a class="link" [routerLink]="['/trace', r.trace_id]">Open full trace</a> }
              </article>
            }
          </section>
        </div>
      }
    </div>

    @if (drawer(); as d) { <app-source-drawer [slug]="d.slug" [chunkText]="d.text" (closed)="drawer.set(null)" /> }

    @if (escalateOpen()) {
      <app-modal title="Escalate this ticket" (closed)="escalateOpen.set(false)">
        <label class="t1-label" for="esc">Handoff note for the next person</label>
        <textarea id="esc" class="t1-textarea" rows="7" [value]="escalateText()" (input)="escalateText.set($any($event.target).value)"></textarea>
        <p class="help">Prefilled with what the assistant already checked, so nobody repeats the work.</p>
        <button modal-actions type="button" class="t1-btn t1-btn--ghost" (click)="escalateOpen.set(false)">Cancel</button>
        <button modal-actions type="button" class="t1-btn t1-btn--danger" [disabled]="busy()" (click)="escalate()">Escalate</button>
      </app-modal>
    }

    @if (feedbackOpen()) {
      <app-modal title="Report a wrong answer" (closed)="feedbackOpen.set(false)">
        <fieldset class="reasons">
          <legend class="t1-label">What was wrong?</legend>
          @for (f of reasons; track f.value) {
            <label class="reason"><input type="radio" name="reason" [value]="f.value" [checked]="feedbackReason() === f.value"
                                         (change)="feedbackReason.set(f.value)" />
              <span><strong>{{ f.label }}</strong><small>{{ f.hint }}</small></span></label>
          }
        </fieldset>
        <label class="t1-label" for="fbc">Anything else? (optional)</label>
        <textarea id="fbc" class="t1-textarea" rows="3" maxlength="500" [value]="feedbackComment()" (input)="feedbackComment.set($any($event.target).value)"></textarea>
        <button modal-actions type="button" class="t1-btn t1-btn--ghost" (click)="feedbackOpen.set(false)">Cancel</button>
        <button modal-actions type="button" class="t1-btn t1-btn--primary" [disabled]="!feedbackReason() || busy()" (click)="sendFeedback()">Send report</button>
      </app-modal>
    }
  `,
  styles: [`
    .ws { padding-top: 1rem; }
    .crumbs { font-size: .8rem; color: var(--text-muted); margin-bottom: .75rem; }
    .seed { font-size: .8rem; color: var(--text-secondary); background: rgba(137,180,250,.08); border: 1px solid rgba(137,180,250,.3); padding: .5rem .75rem; border-radius: var(--radius-md); margin-bottom: .75rem; }
    .grid { display: grid; grid-template-columns: minmax(16rem, 22rem) minmax(0, 1fr) minmax(15rem, 20rem); gap: 1rem; align-items: start; }
    .pane { display: flex; flex-direction: column; gap: .9rem; min-width: 0; }
    .tabs { display: none; gap: .35rem; margin-bottom: .75rem; }
    .tabs button { flex: 1; background: var(--surface-card); border: 1px solid var(--border); color: var(--text-secondary); border-radius: var(--radius-md); padding: .5rem; font: inherit; font-size: .82rem; font-weight: 600; cursor: pointer; }
    .tabs button[aria-selected='true'] { background: var(--accent); border-color: var(--accent); color: #fff; }
    @media (max-width: 1100px) {
      .grid { grid-template-columns: 1fr; }
      .tabs { display: flex; }
      .pane:not(.pane--active) { display: none; }
    }
    .card { background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: .9rem 1rem; }
    .card h2 { font-size: .75rem; text-transform: uppercase; letter-spacing: .05em; color: var(--text-muted); margin-bottom: .55rem; }
    .subject { font-size: 1.05rem; margin-bottom: .5rem; }
    .body { white-space: pre-wrap; line-height: 1.6; font-size: .92rem; }
    dl { margin: 0 0 .8rem; display: grid; gap: .4rem; }
    dl > div { display: grid; grid-template-columns: 5.5rem 1fr; gap: .5rem; font-size: .85rem; }
    dt { color: var(--text-muted); } dd { margin: 0; overflow-wrap: anywhere; }
    .facts dl > div { grid-template-columns: 4rem 1fr; }
    .decided { font-size: .82rem; color: var(--text-secondary); }
    .working { display: flex; align-items: center; gap: .6rem; flex-wrap: wrap; padding: .7rem .9rem; border-radius: var(--radius-md); background: rgba(137,180,250,.08); border: 1px solid rgba(137,180,250,.3); font-size: .88rem; }
    .draft { font-size: .95rem; }
    .edited { margin-left: .4rem; padding: .05rem .4rem; border-radius: var(--radius-sm); background: rgba(250,179,135,.16); color: var(--warning); font-size: .7rem; }
    .help { font-size: .76rem; color: var(--text-muted); margin-top: .3rem; }
    .sources { display: flex; flex-wrap: wrap; gap: .4rem; align-items: center; }
    .sources__label { font-size: .72rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; }
    .source { display: inline-flex; align-items: center; gap: .4rem; background: var(--surface-card); border: 1px solid var(--border-strong); color: var(--text-primary); border-radius: 999px; padding: .25rem .7rem; font: inherit; font-size: .8rem; cursor: pointer; }
    .source:hover { border-color: var(--accent); }
    .source__n { color: var(--accent); font-weight: 700; }
    .block { padding: .6rem .8rem; border-radius: var(--radius-md); border: 1px solid rgba(243,139,168,.5); background: rgba(243,139,168,.08); color: var(--danger); font-size: .85rem; }
    .esc p { font-size: .9rem; line-height: 1.55; } .viol { margin-top: .4rem; color: var(--text-secondary); font-size: .82rem; }
    .blocked { white-space: pre-wrap; background: var(--surface-base); padding: .7rem; border-radius: var(--radius-md); font-size: .84rem; margin-top: .5rem; }
    details summary { cursor: pointer; margin-top: .7rem; font-size: .84rem; color: var(--accent); }
    .actions { position: sticky; bottom: 0; display: flex; flex-wrap: wrap; gap: .5rem; padding: .75rem 0; background: linear-gradient(transparent, var(--surface-base) 30%); }
    .kbd-on { background: rgba(255,255,255,.18); border-color: rgba(255,255,255,.4); color: #fff; }
    .link { background: none; border: 0; color: var(--accent); cursor: pointer; font: inherit; font-size: .8rem; padding: 0 .3rem; }
    .reasons { border: 0; padding: 0; margin: 0 0 .8rem; display: grid; gap: .4rem; }
    .reason { display: flex; gap: .6rem; align-items: flex-start; padding: .5rem .6rem; border: 1px solid var(--border); border-radius: var(--radius-md); cursor: pointer; }
    .reason span { display: flex; flex-direction: column; font-size: .88rem; } .reason small { color: var(--text-muted); font-size: .76rem; }
    .sk-head { height: 2rem; width: 40%; margin-bottom: 1rem; } .sk-body { height: 16rem; } .sk-draft { height: 14rem; margin-top: .8rem; }
  `],
})
export class TicketWorkspaceComponent {
  private api = inject(Tier1Service);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private toast = inject(ToastService);
  private destroyRef = inject(DestroyRef);
  auth = inject(AuthService);

  @ViewChild('editor') editor?: ElementRef<HTMLTextAreaElement>;

  id = '';
  get reasons() { return feedbackReasons(); }
  detail = signal<TicketDetail | null>(null);
  claimTopics = signal<RegExp | null>(null);
  private _rule = this.api.claimTopics().subscribe({ next: r => this.claimTopics.set(new RegExp(r.claim_topics, 'i')), error: () => undefined });
  loadError = signal(false);
  result = signal<TicketAnswer | null>(null);
  steps = signal<Step[]>([]);
  running = signal(false);
  jobError = signal<string | null>(null);
  traceId = signal('');
  draft = signal('');
  original = signal('');
  busy = signal(false);
  tab = signal<'ticket' | 'draft' | 'steps'>('draft');
  seed = signal<number | null>(null);
  drawer = signal<{ slug: string; text: string } | null>(null);
  escalateOpen = signal(false);
  escalateText = signal('');
  feedbackOpen = signal(false);
  feedbackReason = signal('');
  feedbackComment = signal('');
  private job?: Subscription;
  private autoRun = false;

  dirty = computed(() => this.draft() !== this.original());
  lastDecision = computed(() => this.detail()?.decisions[0] ?? null);
  sources = computed(() => numberedSources(this.original(), this.result()?.citations ?? []));
  needsEntitlement = computed(() => {
    const r = this.result();
    const rule = this.claimTopics();
    return !!r && r.decision === 'ANSWER' && !r.entitlement && !!rule && rule.test(this.draft());
  });
  canApprove = computed(() => {
    const r = this.result();
    return !!r && r.decision === 'ANSWER' && !!this.draft().trim() && !this.needsEntitlement() && !this.busy() && !this.running();
  });

  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(p => {
      this.id = p.get('id') ?? '';
      this.autoRun = this.route.snapshot.queryParamMap.get('run') === '1';
      const seed = this.route.snapshot.queryParamMap.get('seed');
      this.seed.set(seed === null ? null : Number(seed));
      this.load();
    });
    this.destroyRef.onDestroy(() => this.job?.unsubscribe());
  }

  load(): void {
    this.loadError.set(false);
    this.api.ticket(this.id).subscribe({
      next: d => {
        this.detail.set(d);
        if (d.ai && !this.running()) this.setResult(d.ai);
        if (!d.ai && this.autoRun && !this.running()) { this.autoRun = false; this.run(); }
      },
      error: () => this.loadError.set(true),
    });
  }

  private setResult(r: TicketAnswer): void {
    this.result.set(r);
    const text = r.customer_reply || r.reply;
    this.draft.set(text);
    this.original.set(text);
    this.traceId.set(r.trace_id);
  }

  run(): void {
    this.job?.unsubscribe();
    this.running.set(true);
    this.jobError.set(null);
    this.steps.set([]);
    this.result.set(null);
    this.tab.set('draft');
    this.api.answer({ ticket_id: this.id }).subscribe({
      next: ({ job_id, trace_id }) => {
        this.traceId.set(trace_id);
        this.job = this.api.pollJob(job_id).subscribe({
          next: j => {
            this.steps.set(j.steps);
            if (j.status === 'done' && j.result) { this.setResult(j.result); this.running.set(false); this.load(); }
            if (j.status === 'error') { this.jobError.set(j.error ?? 'The assistant could not finish this ticket.'); this.running.set(false); }
          },
          error: () => { this.jobError.set('Lost contact with the server while the assistant was working.'); this.running.set(false); },
        });
      },
      error: err => {
        this.running.set(false);
        this.jobError.set(err.status === 429
          ? 'The assistant is busy with other tickets. Wait a minute and run it again.'
          : 'The assistant could not be started.');
      },
    });
  }

  cancel(): void { this.job?.unsubscribe(); this.running.set(false); this.toast.show('Stopped waiting. The assistant may still finish in the background.'); }

  regenerate(): void {
    if (this.dirty() && !window.confirm('You have edited the draft. Running the assistant again will replace your edits. Continue?')) return;
    this.run();
  }

  approve(): void {
    if (!this.canApprove()) return;
    this.busy.set(true);
    const text = this.draft();
    const copied = navigator.clipboard?.writeText(text);
    (copied ?? Promise.reject()).then(
      () => this.toast.success('Reply copied. Paste it into your email or chat.'),
      () => this.toast.show('Could not copy automatically. Select the draft and copy it by hand.', 'info'),
    );
    this.api.decide(this.id, 'approve', text).subscribe({
      next: res => { this.busy.set(false); this.toast.success(res.action === 'edit' ? 'Saved as edited.' : 'Approved as drafted.'); this.load(); },
      error: () => { this.busy.set(false); this.toast.error('The decision could not be saved. Try again.'); },
    });
  }

  openEscalate(): void {
    const r = this.result();
    const checked = r?.tools_called.length ? `Checked: ${r.tools_called.join(', ')}.` : 'No checks were made.';
    const why = r?.decision === 'ESCALATE' ? `Assistant recommendation: ${reasonLabel(r.reason)}.` : '';
    this.escalateText.set(`Customer asked: ${this.detail()?.subject || 'see ticket'}. ${why} ${checked}`.replace(/\s+/g, ' ').trim());
    this.escalateOpen.set(true);
  }

  escalate(): void {
    this.busy.set(true);
    this.api.decide(this.id, 'escalate', this.escalateText()).subscribe({
      next: () => { this.busy.set(false); this.escalateOpen.set(false); this.toast.success('Escalated. It is in the escalation queue.'); this.load(); },
      error: () => { this.busy.set(false); this.toast.error('Could not escalate. Try again.'); },
    });
  }

  sendFeedback(): void {
    const r = this.result();
    if (!r) return;
    this.busy.set(true);
    this.api.sendFeedback({ trace_id: r.trace_id, ticket_id: this.id, reason: this.feedbackReason(), comment: this.feedbackComment() || undefined })
      .subscribe({
        next: () => { this.busy.set(false); this.feedbackOpen.set(false); this.feedbackReason.set(''); this.feedbackComment.set('');
                      this.toast.success('Thanks. A team lead will review it and it can become a permanent test.'); },
        error: () => { this.busy.set(false); this.toast.error('The report could not be sent.'); },
      });
  }

  openSource(slug: string): void {
    const chunk = this.result()?.sources.find(s => s.slug === slug);
    this.drawer.set({ slug, text: chunk?.text ?? '' });
  }

  focusEditor(): void { this.tab.set('draft'); queueMicrotask(() => this.editor?.nativeElement.focus()); }
  copyTrace(id: string): void { navigator.clipboard?.writeText(id).then(() => this.toast.show('Trace id copied.')); }
  why(reason: string): string { return reasonLabel(reason); }
  cost(v: number): string { return usd(v); }
  decisionWord(a: string): string { return refLabel('decision', a); }

  @HostListener('document:keydown', ['$event'])
  onKey(e: KeyboardEvent): void {
    if (this.escalateOpen() || this.feedbackOpen() || this.drawer()) return;
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); this.approve(); return; }
    const t = e.target as HTMLElement;
    if (e.ctrlKey || e.metaKey || e.altKey || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable) return;
    if (e.key === 'E' && e.shiftKey) { e.preventDefault(); this.openEscalate(); }
    else if (e.key === 'e') { e.preventDefault(); this.focusEditor(); }
    else if (e.key === 'r') { e.preventDefault(); this.result() ? this.regenerate() : this.run(); }
  }
}
