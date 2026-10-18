import { ChangeDetectionStrategy, Component, HostListener, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AgreementResponse, Label, LabelItem, Tier1Service } from '../../services/tier1.service';
import { EmptyStateComponent, ErrorStateComponent } from '../../shared/primitives';
import { EntitlementCardComponent } from '../../shared/entitlement-card.component';
import { SourceDrawerComponent } from '../../shared/source-drawer.component';
import { ToastService } from '../../shared/toast';
import { refLabel } from '../../shared/ref-data';

/**
 * A person labels the assistant's replies GOOD or NOT_GOOD, so the judge can be checked against a human.
 * The judge's verdict and the assertion results are never sent to this page: seeing them would anchor the label.
 * Agreement stays hidden until enough labels exist, for the same reason.
 */
@Component({
  selector: 'app-label-replies',
  standalone: true,
  imports: [FormsModule, EmptyStateComponent, ErrorStateComponent, EntitlementCardComponent, SourceDrawerComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="t1-page">
      <div class="t1-page__head">
        <div>
          <h1 class="t1-h1">Label replies</h1>
          <p class="t1-sub">Would a Tier-1 lead send this reply as written? Your labels check whether the automatic judge can be trusted.</p>
        </div>
        @if (runs().length > 1) {
          <label class="run">Run
            <select [ngModel]="tag()" (ngModelChange)="pickRun($event)" aria-label="Eval run to label">
              @for (r of runs(); track r.tag) { <option [value]="r.tag">{{ r.tag }} ({{ r.answers }} replies)</option> }
            </select>
          </label>
        }
      </div>

      @if (error()) {
        <app-error-state message="The replies could not be loaded." retryLabel="Try again" (retry)="init()" />
      } @else if (loading()) {
        <div class="t1-skeleton sk"></div>
      } @else if (!tag()) {
        <app-empty-state title="Nothing to label yet" detail="Labels need an evaluation run with the judge on. Run: python -m tier1 eval --tag fix1" />
      } @else if (!labeler()) {
        <form class="card who" (ngSubmit)="saveLabeler()">
          <h2>Before you start</h2>
          <p>Your name and your support-queue experience are stored with the labels, so the report can say who labelled.</p>
          <label>Your name <input name="name" [(ngModel)]="nameInput" required minlength="2" autocomplete="name" /></label>
          <label>Queue experience <input name="exp" [(ngModel)]="expInput" required minlength="2" placeholder="for example: 2 years on Tier-1 billing" /></label>
          <button type="submit" class="t1-btn t1-btn--primary" [disabled]="nameInput.trim().length < 2 || expInput.trim().length < 2">Start labelling</button>
        </form>
      } @else {
        <div class="progress" role="group" aria-label="Progress">
          <div class="bar" role="progressbar" [attr.aria-valuenow]="labelled()" aria-valuemin="0" [attr.aria-valuemax]="items().length">
            <span [style.width.%]="items().length ? labelled() / items().length * 100 : 0"></span>
          </div>
          <span>{{ labelled() }} of {{ items().length }} labelled. Agreement unlocks at {{ minLabels() }}.</span>
        </div>

        @if (current(); as it) {
          <section class="card item" aria-live="polite">
            <header class="item__head">
              <span class="pos">Reply {{ index() + 1 }} of {{ items().length }}</span>
              <code>{{ it.case_id }}</code>
              @if (it.label) { <span class="mine" [attr.data-l]="it.label">You said {{ word(it.label) }}</span> }
            </header>

            <h2 class="h">The ticket</h2>
            <p class="subject">{{ it.subject }}</p>
            <p class="body">{{ it.body }}</p>

            @if (it.account_facts.entitlement) { <app-entitlement-card [entitlement]="it.account_facts.entitlement" /> }
            @if (it.account_facts.order) {
              <p class="order"><strong>Order record:</strong> {{ orderLine(it.account_facts.order) }}</p>
            }

            <h2 class="h">The reply the customer would get</h2>
            <blockquote class="reply">{{ it.reply }}</blockquote>

            <h2 class="h">Sources the assistant had</h2>
            <div class="sources">
              @for (s of it.sources; track s.chunk_id) {
                <button type="button" class="chip" (click)="openSource(s.slug, s.text)">{{ s.slug }}</button>
              }
            </div>

            <div class="actions">
              <button type="button" class="t1-btn" (click)="prev()" [disabled]="index() === 0">Previous</button>
              <span class="grow"></span>
              <button type="button" class="t1-btn" (click)="label(null)" title="Keyboard: S">Skip <kbd>S</kbd></button>
              <button type="button" class="t1-btn t1-btn--danger" (click)="label('NOT_GOOD')" [disabled]="saving()" title="Keyboard: N">Not good <kbd>N</kbd></button>
              <button type="button" class="t1-btn t1-btn--primary" (click)="label('GOOD')" [disabled]="saving()" title="Keyboard: G">Good <kbd>G</kbd></button>
            </div>
          </section>
          <p class="hint">GOOD means a lead would send it as written: right for this customer's policy and order, nothing invented,
            answers the question, and never says a refund has been issued.</p>
        } @else {
          <app-empty-state title="All replies seen" detail="Use Previous to change a label, or check agreement below." />
        }

        <section class="card agree">
          <div class="agree__head">
            <h2>Judge agreement</h2>
            <button type="button" class="t1-btn" (click)="loadAgreement()" [disabled]="labelled() < minLabels()">Check agreement</button>
          </div>
          @if (agreement(); as a) {
            @if (a.status === 'locked') {
              <p class="muted">Locked until {{ a.min_labels }} replies are labelled ({{ a.labelled }} so far).</p>
            } @else {
              @for (j of judgeRows(a); track j.key) {
                <p><strong>{{ j.title }}</strong> ({{ j.version }}):
                  {{ j.agree }} of {{ j.n }} agree = <span [attr.data-ok]="j.ok">{{ j.pct }}%</span>
                  (target {{ targetPct() }}%). Judge said GOOD where you said NOT GOOD: {{ j.danger }}.</p>
              }
              <p class="muted">The report picks this up with: python -m tier1 eval --rescore {{ tag() }}</p>
            }
          } @else {
            <p class="muted">Label at least {{ minLabels() }} replies, then check. The number stays hidden until then so it cannot steer your labels.</p>
          }
        </section>
      }
    </div>
    @if (drawer(); as d) { <app-source-drawer [slug]="d.slug" [chunkText]="d.text" (closed)="drawer.set(null)" /> }
  `,
  styles: [`
    .sk { height: 18rem; }
    .run { display: flex; gap: .5rem; align-items: center; font-size: .85rem; color: var(--text-secondary); }
    .run select, .who input { background: var(--surface-base); color: var(--text-primary); border: 1px solid var(--border); border-radius: var(--radius-md); padding: .45rem .6rem; font: inherit; }
    .card { background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 1rem 1.1rem; margin-bottom: 1rem; }
    .who { display: grid; gap: .8rem; max-width: 30rem; } .who label { display: grid; gap: .3rem; font-size: .88rem; }
    .who h2, .agree h2 { font-size: 1rem; margin: 0; }
    .progress { display: flex; flex-wrap: wrap; gap: .6rem 1rem; align-items: center; margin-bottom: 1rem; font-size: .85rem; color: var(--text-secondary); }
    .bar { flex: 1 1 12rem; height: .55rem; background: var(--surface-base); border-radius: 999px; overflow: hidden; }
    .bar span { display: block; height: 100%; background: var(--accent); transition: width .2s; }
    .item__head { display: flex; flex-wrap: wrap; gap: .5rem .9rem; align-items: baseline; margin-bottom: .4rem; }
    .pos { font-size: .75rem; text-transform: uppercase; letter-spacing: .05em; color: var(--text-muted); font-weight: 700; }
    .mine { font-size: .8rem; font-weight: 600; } .mine[data-l='GOOD'] { color: var(--success); } .mine[data-l='NOT_GOOD'] { color: var(--danger); }
    .h { font-size: .75rem; text-transform: uppercase; letter-spacing: .05em; color: var(--text-muted); margin: 1rem 0 .4rem; }
    .subject { font-weight: 600; margin: 0; } .body { white-space: pre-wrap; color: var(--text-secondary); margin: .3rem 0 .8rem; line-height: 1.55; }
    .order { font-size: .88rem; color: var(--text-secondary); }
    .reply { white-space: pre-wrap; margin: 0; padding: .8rem 1rem; border-left: 3px solid var(--accent); background: var(--surface-base); border-radius: var(--radius-md); line-height: 1.6; }
    .sources { display: flex; flex-wrap: wrap; gap: .4rem; }
    .chip { background: var(--surface-base); border: 1px solid var(--border); color: var(--text-primary); border-radius: 999px; padding: .25rem .7rem; font: inherit; font-size: .8rem; cursor: pointer; }
    .actions { display: flex; flex-wrap: wrap; gap: .5rem; margin-top: 1.2rem; align-items: center; } .grow { flex: 1; }
    kbd { font-size: .7rem; opacity: .7; margin-left: .25rem; border: 1px solid currentColor; border-radius: 3px; padding: 0 .25rem; }
    .hint, .muted { color: var(--text-muted); font-size: .84rem; }
    .agree__head { display: flex; justify-content: space-between; align-items: center; gap: .5rem; flex-wrap: wrap; margin-bottom: .4rem; }
    [data-ok='true'] { color: var(--success); font-weight: 700; } [data-ok='false'] { color: var(--danger); font-weight: 700; }
  `],
})
export class LabelRepliesComponent implements OnInit {
  private api = inject(Tier1Service);
  private toast = inject(ToastService);

  runs = signal<{ tag: string; answers: number }[]>([]);
  tag = signal('');
  items = signal<LabelItem[]>([]);
  index = signal(0);
  labeler = signal('');
  minLabels = signal(0);
  target = signal(0);
  targetPct = computed(() => Math.round(this.target() * 100));
  loading = signal(true);
  error = signal(false);
  saving = signal(false);
  agreement = signal<AgreementResponse | null>(null);
  drawer = signal<{ slug: string; text: string } | null>(null);
  nameInput = '';
  expInput = '';

  current = computed(() => this.items()[this.index()] ?? null);
  labelled = computed(() => this.items().filter(i => i.label).length);

  ngOnInit(): void { this.init(); }

  init(): void {
    this.loading.set(true); this.error.set(false);
    this.api.labelRuns().subscribe({
      next: runs => {
        this.runs.set(runs);
        if (!runs.length) { this.loading.set(false); return; }
        this.pickRun(runs[0].tag);
      },
      error: () => { this.error.set(true); this.loading.set(false); },
    });
  }

  pickRun(tag: string): void {
    this.tag.set(tag); this.agreement.set(null); this.loading.set(true);
    this.api.labelQueue(tag).subscribe({
      next: q => {
        this.items.set(q.items); this.labeler.set(q.labeler); this.minLabels.set(q.min_labels); this.target.set(q.target);
        const firstOpen = q.items.findIndex(i => !i.label);
        this.index.set(firstOpen < 0 ? q.items.length : firstOpen);
        this.loading.set(false);
      },
      error: () => { this.error.set(true); this.loading.set(false); },
    });
  }

  saveLabeler(): void {
    this.api.setLabeler(this.nameInput, this.expInput).subscribe({
      next: r => this.labeler.set(r.labeler),
      error: () => this.toast.error('Could not save your name. Check both fields.'),
    });
  }

  label(value: Label | null): void {
    const it = this.current();
    if (!it || this.saving()) return;
    if (value === null && !it.label) { this.next(); return; }       // skipping an unlabelled reply needs no request
    this.saving.set(true);
    this.api.setLabel(this.tag(), it.case_id, value).subscribe({
      next: () => {
        this.items.update(list => list.map(i => i.case_id === it.case_id ? { ...i, label: value } : i));
        this.saving.set(false); this.next();
      },
      error: () => { this.saving.set(false); this.toast.error('The label was not saved. Try again.'); },
    });
  }

  next(): void { this.index.update(i => Math.min(i + 1, this.items().length)); }
  prev(): void { this.index.update(i => Math.max(i - 1, 0)); }

  loadAgreement(): void {
    this.api.labelAgreement(this.tag()).subscribe({
      next: a => this.agreement.set(a),
      error: () => this.toast.error('Agreement could not be computed.'),
    });
  }

  judgeRows(a: AgreementResponse): { key: string; title: string; version: string; n: number; agree: number; pct: number; ok: boolean; danger: number }[] {
    return Object.entries(a.judges ?? {}).map(([key, j]) => ({
      key, title: refLabel('judge_role', key), version: j.version, n: j.n, agree: j.agree ?? 0,
      pct: Math.round((j.agreement ?? 0) * 100), ok: !!j.meets_target, danger: j.judge_good_human_not_good ?? 0,
    }));
  }

  openSource(slug: string, text: string): void { this.drawer.set({ slug, text }); }
  word(l: Label): string { return l === 'GOOD' ? 'good' : 'not good'; }
  orderLine(o: Record<string, unknown>): string {
    return ['order_id', 'status', 'purchase_date', 'days_since_purchase', 'amount', 'currency'].filter(k => o[k] !== undefined && o[k] !== null)
      .map(k => `${k.split('_').join(' ')}: ${o[k]}`).join(', ');
  }

  @HostListener('document:keydown', ['$event'])
  onKey(e: KeyboardEvent): void {
    const target = e.target as HTMLElement | null;
    if (this.drawer() || !this.labeler() || e.ctrlKey || e.metaKey || e.altKey) return;
    if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return;
    const key = e.key.toLowerCase();
    if (key === 'g') { e.preventDefault(); this.label('GOOD'); }
    else if (key === 'n') { e.preventDefault(); this.label('NOT_GOOD'); }
    else if (key === 's') { e.preventDefault(); this.label(null); }
  }
}
