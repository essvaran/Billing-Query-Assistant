import { ChangeDetectionStrategy, Component, DestroyRef, ElementRef, HostListener, ViewChild, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { QueueItem, QueueResponse, Tier1Service, TicketStatus } from '../../services/tier1.service';
import { EmptyStateComponent, ErrorStateComponent, PolicyBadgeComponent, StatusChipComponent } from '../../shared/primitives';
import { ModalComponent } from '../../shared/modal.component';
import { queueStatuses, reasonLabel, statusLabel } from '../../shared/labels';
import { refValues } from '../../shared/ref-data';


@Component({
  selector: 'app-ticket-queue',
  standalone: true,
  imports: [RouterLink, StatusChipComponent, PolicyBadgeComponent, EmptyStateComponent, ErrorStateComponent, ModalComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="t1-page">
      <div class="t1-page__head">
        <div>
          <h1 class="t1-h1">Tickets</h1>
          <p class="t1-sub">The assistant drafts; you decide. Open a ticket to review the draft, its sources and what was checked.</p>
        </div>
        <div class="head__actions">
          <button type="button" class="t1-btn t1-btn--ghost" (click)="showKeys.set(true)">Keyboard shortcuts <span class="t1-kbd">?</span></button>
          <a class="t1-btn" routerLink="/try">Try a ticket</a>
        </div>
      </div>

      <div class="filters" role="group" aria-label="Filter tickets">
        <div class="status-tabs" role="tablist" aria-label="Status">
          <button type="button" role="tab" class="tab" [attr.aria-selected]="!status" (click)="setQuery({ status: '' })">
            All <span class="tab__n">{{ totalAll() }}</span>
          </button>
          @for (s of statuses; track s) {
            <button type="button" role="tab" class="tab" [attr.aria-selected]="status === s" (click)="setQuery({ status: s })">
              {{ label(s) }} <span class="tab__n">{{ data()?.counts?.[s] ?? 0 }}</span>
            </button>
          }
        </div>
        <div class="filters__row">
          <label class="sr-only" for="q">Search tickets</label>
          <input #search id="q" class="t1-input search" type="search" placeholder="Search subject or text  ( / )"
                 [value]="q" (input)="onSearch($any($event.target).value)" />
          <label class="sr-only" for="policy">Refund policy</label>
          <select id="policy" class="t1-select" [value]="policy" (change)="setQuery({ policy: $any($event.target).value })">
            <option value="">Any policy</option>
            @for (p of policies(); track p.code) { <option [value]="p.code">{{ p.label }}</option> }
          </select>
          <label class="sr-only" for="region">Region</label>
          <select id="region" class="t1-select" [value]="region" (change)="setQuery({ region: $any($event.target).value })">
            <option value="">Any region</option>
            @for (r of regions(); track r.code) { <option [value]="r.code">{{ r.label }}</option> }
          </select>
          @if (hasFilters) { <button type="button" class="t1-btn t1-btn--ghost" (click)="clear()">Clear filters</button> }
        </div>
      </div>

      @if (error()) {
        <app-error-state message="The ticket list could not be loaded." retryLabel="Try again" (retry)="load()" />
      } @else {
        <div class="table-wrap">
          <table class="table" aria-label="Tickets" [attr.aria-busy]="loading()">
            <thead>
              <tr><th>Status</th><th>Ticket</th><th>Customer</th><th>Policy</th><th>Region</th><th class="num">Order age</th></tr>
            </thead>
            <tbody>
              @if (loading() && !data()) {
                @for (i of skeletonRows; track i) {
                  <tr aria-hidden="true"><td colspan="6"><div class="t1-skeleton skel"></div></td></tr>
                }
              }
              @for (t of data()?.items ?? []; track t.ticket_id; let i = $index) {
                <tr class="row" [class.row--focus]="focused() === i" (click)="open(t)" (mouseenter)="focused.set(i)">
                  <td><app-status-chip [status]="t.status" />
                    @if (t.ai_reason) { <div class="reason">{{ reason(t.ai_reason) }}</div> }</td>
                  <td class="subject">
                    <a [routerLink]="['/tickets', t.ticket_id]" (click)="$event.stopPropagation()">{{ t.subject || t.ticket_id }}</a>
                    <div class="preview">{{ t.preview }}</div>
                  </td>
                  <td>{{ t.customer }}<div class="preview">{{ t.customer_email }}</div></td>
                  <td><app-policy-badge [version]="t.policy_version" /></td>
                  <td>{{ t.region }}</td>
                  <td class="num">{{ t.order_age_days }} days</td>
                </tr>
              }
            </tbody>
          </table>
          @if (!loading() && data() && data()!.items.length === 0) {
            <app-empty-state title="No tickets match" detail="Try a different search, or clear the filters to see everything.">
              <button type="button" class="t1-btn" (click)="clear()">Clear filters</button>
            </app-empty-state>
          }
        </div>

        @if (data(); as d) {
          @if (d.total > d.page_size) {
            <nav class="pager" aria-label="Pages">
              <button type="button" class="t1-btn" [disabled]="page <= 1" (click)="setQuery({ page: page - 1 })">Previous</button>
              <span>Page {{ page }} of {{ pages(d) }} ({{ d.total }} tickets)</span>
              <button type="button" class="t1-btn" [disabled]="page >= pages(d)" (click)="setQuery({ page: page + 1 })">Next</button>
            </nav>
          }
        }
      }
    </div>

    @if (showKeys()) {
      <app-modal title="Keyboard shortcuts" (closed)="showKeys.set(false)">
        <dl class="keys">
          <div><dt><span class="t1-kbd">j</span> <span class="t1-kbd">k</span></dt><dd>Move down and up the list</dd></div>
          <div><dt><span class="t1-kbd">Enter</span></dt><dd>Open the highlighted ticket</dd></div>
          <div><dt><span class="t1-kbd">/</span></dt><dd>Search</dd></div>
          <div><dt><span class="t1-kbd">?</span></dt><dd>Show this help</dd></div>
        </dl>
        <button modal-actions type="button" class="t1-btn t1-btn--primary" (click)="showKeys.set(false)">Done</button>
      </app-modal>
    }
  `,
  styles: [`
    .head__actions { display: flex; gap: .5rem; flex-wrap: wrap; }
    .filters { display: flex; flex-direction: column; gap: .75rem; margin-bottom: 1rem; }
    .status-tabs { display: flex; flex-wrap: wrap; gap: .35rem; }
    .tab { background: var(--surface-card); border: 1px solid var(--border); color: var(--text-secondary); border-radius: 999px;
      padding: .35rem .8rem; font: inherit; font-size: .82rem; font-weight: 600; cursor: pointer; }
    .tab[aria-selected='true'] { background: var(--accent); border-color: var(--accent); color: #fff; }
    .tab__n { opacity: .8; margin-left: .25rem; font-weight: 500; }
    .filters__row { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; }
    .search { flex: 1 1 16rem; }
    .table-wrap { background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-lg); overflow-x: auto; }
    .table { width: 100%; border-collapse: collapse; font-size: .88rem; }
    th { text-align: left; font-size: .72rem; text-transform: uppercase; letter-spacing: .05em; color: var(--text-muted); padding: .7rem .9rem; border-bottom: 1px solid var(--border); white-space: nowrap; }
    td { padding: .7rem .9rem; border-bottom: 1px solid var(--border); vertical-align: top; }
    tr:last-child td { border-bottom: 0; }
    .num { text-align: right; white-space: nowrap; }
    .row { cursor: pointer; }
    .row--focus, .row:hover { background: rgba(137,180,250,.08); }
    .row--focus { box-shadow: inset 3px 0 0 var(--accent); }
    .subject a { font-weight: 600; color: var(--text-primary); }
    .preview { font-size: .78rem; color: var(--text-muted); margin-top: .15rem; max-width: 34rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .reason { font-size: .72rem; color: var(--text-muted); margin-top: .2rem; max-width: 12rem; }
    .skel { height: 2.4rem; margin: .2rem 0; }
    .pager { display: flex; gap: 1rem; align-items: center; justify-content: center; margin-top: 1rem; font-size: .85rem; color: var(--text-secondary); }
    .keys { margin: 0; display: grid; gap: .6rem; }
    .keys div { display: grid; grid-template-columns: 8rem 1fr; gap: .75rem; align-items: center; }
    .keys dd { margin: 0; color: var(--text-secondary); font-size: .88rem; }
  `],
})
export class TicketQueueComponent {
  private api = inject(Tier1Service);
  private router = inject(Router);
  private route = inject(ActivatedRoute);
  private destroyRef = inject(DestroyRef);

  @ViewChild('search') searchBox?: ElementRef<HTMLInputElement>;

  get statuses(): TicketStatus[] { return queueStatuses() as TicketStatus[]; }
  regions() { return refValues('region'); }
  policies() { return refValues('policy_version').filter(v => v.code !== 'none'); }
  skeletonRows = [1, 2, 3, 4, 5, 6];
  data = signal<QueueResponse | null>(null);
  loading = signal(true);
  error = signal(false);
  focused = signal(0);
  showKeys = signal(false);

  status = ''; q = ''; policy = ''; region = ''; page = 1;
  private searchTimer?: ReturnType<typeof setTimeout>;

  constructor() {
    this.route.queryParams.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(p => {
      this.status = p['status'] ?? ''; this.q = p['q'] ?? ''; this.policy = p['policy'] ?? '';
      this.region = p['region'] ?? ''; this.page = Number(p['page'] ?? 1) || 1;
      this.load();
    });
  }

  load(): void {
    this.loading.set(true);
    this.error.set(false);
    this.api.tickets({ status: this.status, q: this.q, policy: this.policy, region: this.region, page: this.page })
      .subscribe({
        next: d => { this.data.set(d); this.loading.set(false); this.focused.set(0); },
        error: () => { this.error.set(true); this.loading.set(false); },
      });
  }

  /** Filters live in the URL, so a link reproduces exactly the view someone is looking at. */
  setQuery(change: Record<string, string | number>): void {
    const reset = 'page' in change ? {} : { page: null };
    this.router.navigate([], { queryParams: { ...change, ...reset }, queryParamsHandling: 'merge' });
  }
  onSearch(value: string): void {
    clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => this.setQuery({ q: value }), 300);
  }
  clear(): void {
    this.router.navigate([], { queryParams: { status: null, q: null, policy: null, region: null, page: null } });
  }
  get hasFilters(): boolean { return !!(this.status || this.q || this.policy || this.region); }

  label(s: TicketStatus): string { return statusLabel(s); }
  reason(r: string): string { return reasonLabel(r); }
  totalAll(): number { return Object.values(this.data()?.counts ?? {}).reduce((a, b) => a + (b ?? 0), 0); }
  pages(d: QueueResponse): number { return Math.max(1, Math.ceil(d.total / d.page_size)); }
  open(t: QueueItem): void { this.router.navigate(['/tickets', t.ticket_id]); }

  @HostListener('document:keydown', ['$event'])
  onKey(e: KeyboardEvent): void {
    const target = e.target as HTMLElement;
    if (e.ctrlKey || e.metaKey || e.altKey || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName) || target.isContentEditable) return;
    const items = this.data()?.items ?? [];
    if (e.key === 'j') this.focused.update(i => Math.min(items.length - 1, i + 1));
    else if (e.key === 'k') this.focused.update(i => Math.max(0, i - 1));
    else if (e.key === 'Enter' && items[this.focused()] && target.tagName !== 'A' && target.tagName !== 'BUTTON') this.open(items[this.focused()]);
    else if (e.key === '/') { e.preventDefault(); this.searchBox?.nativeElement.focus(); }
    else if (e.key === '?') this.showKeys.set(true);
  }
}
