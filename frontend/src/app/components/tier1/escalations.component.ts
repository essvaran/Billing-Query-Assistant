import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { Escalation, Tier1Service } from '../../services/tier1.service';
import { EmptyStateComponent, ErrorStateComponent } from '../../shared/primitives';
import { ToastService } from '../../shared/toast';
import { reasonLabel } from '../../shared/labels';
import { refLabel, refValues } from '../../shared/ref-data';

type Filter = 'queued' | 'claimed' | 'resolved' | '';

/** Handoffs from the assistant and from agents. Each card says what was already checked, so nobody redoes it. */
@Component({
  selector: 'app-escalations',
  standalone: true,
  imports: [RouterLink, DatePipe, EmptyStateComponent, ErrorStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="t1-page">
      <div class="t1-page__head">
        <div>
          <h1 class="t1-h1">Escalations</h1>
          <p class="t1-sub">Tickets the assistant would not answer, and tickets agents handed over. Claim one to work on it.</p>
        </div>
        <button type="button" class="t1-btn" (click)="load()">Refresh</button>
      </div>

      <div class="tabs" role="tablist" aria-label="Status">
        @for (t of tabs; track t.value) {
          <button type="button" role="tab" [attr.aria-selected]="filter() === t.value" (click)="setFilter(t.value)">{{ t.label }}</button>
        }
      </div>

      @if (error()) {
        <app-error-state message="The escalation queue could not be loaded." retryLabel="Try again" (retry)="load()" />
      } @else if (loading() && !items().length) {
        <div class="t1-skeleton sk"></div><div class="t1-skeleton sk"></div><div class="t1-skeleton sk"></div>
      } @else if (!items().length) {
        <app-empty-state title="Nothing here" [detail]="filter() === 'queued' ? 'No ticket is waiting for a person right now.' : 'No escalations in this state.'" />
      } @else {
        <ul class="list">
          @for (e of items(); track e.handoff_id) {
            <li class="item" [attr.data-status]="e.status">
              <div class="item__top">
                <span class="status">{{ statusWord(e.status) }}</span>
                <strong>{{ why(e.reason) }}</strong>
                <span class="when">{{ e.created_at | date: 'MMM d, HH:mm' }}</span>
              </div>
              <p class="summary">{{ e.summary }}</p>
              <div class="item__foot">
                @if (isTicket(e.ticket_ref)) { <a [routerLink]="['/tickets', e.ticket_ref]">Open ticket {{ e.ticket_ref }}</a> }
                @else { <span class="ref">{{ e.ticket_ref }}</span> }
                @if (e.claimed_by) { <span class="ref">{{ e.status }} by {{ e.claimed_by }}</span> }
                <span class="grow"></span>
                @if (e.status === 'queued') { <button type="button" class="t1-btn" (click)="update(e, 'claimed')">Claim</button> }
                @if (e.status !== 'resolved') { <button type="button" class="t1-btn t1-btn--primary" (click)="update(e, 'resolved')">Mark resolved</button> }
              </div>
            </li>
          }
        </ul>
      }
    </div>
  `,
  styles: [`
    .tabs { display: flex; gap: .35rem; margin-bottom: 1rem; flex-wrap: wrap; }
    .tabs button { background: var(--surface-card); border: 1px solid var(--border); color: var(--text-secondary); border-radius: 999px; padding: .35rem .85rem; font: inherit; font-size: .82rem; font-weight: 600; cursor: pointer; }
    .tabs button[aria-selected='true'] { background: var(--accent); border-color: var(--accent); color: #fff; }
    .list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: .7rem; }
    .item { background: var(--surface-card); border: 1px solid var(--border); border-left: 4px solid var(--warning); border-radius: var(--radius-lg); padding: .85rem 1rem; }
    .item[data-status='claimed'] { border-left-color: var(--accent); } .item[data-status='resolved'] { border-left-color: var(--success); opacity: .8; }
    .item__top { display: flex; flex-wrap: wrap; gap: .5rem .8rem; align-items: baseline; }
    .status { font-size: .7rem; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--text-muted); }
    .when { margin-left: auto; font-size: .78rem; color: var(--text-muted); }
    .summary { margin: .45rem 0 .7rem; font-size: .9rem; color: var(--text-secondary); line-height: 1.55; }
    .item__foot { display: flex; flex-wrap: wrap; gap: .5rem .8rem; align-items: center; font-size: .82rem; }
    .grow { flex: 1; } .ref { color: var(--text-muted); }
    .sk { height: 5rem; margin-bottom: .7rem; }
  `],
})
export class EscalationsComponent implements OnInit {
  private api = inject(Tier1Service);
  private toast = inject(ToastService);

  get tabs(): { value: Filter; label: string }[] {
    return [...refValues('escalation_status').map(v => ({ value: v.code as Filter, label: v.label })), { value: '' as Filter, label: 'All' }];
  }
  filter = signal<Filter>('queued');
  items = signal<Escalation[]>([]);
  loading = signal(true);
  error = signal(false);

  ngOnInit(): void { this.load(); }

  load(): void {
    this.loading.set(true); this.error.set(false);
    this.api.escalations(this.filter()).subscribe({
      next: rows => { this.items.set(rows); this.loading.set(false); },
      error: () => { this.error.set(true); this.loading.set(false); },
    });
  }
  setFilter(f: Filter): void { this.filter.set(f); this.load(); }

  update(e: Escalation, status: 'claimed' | 'resolved'): void {
    this.api.escalationStatus(e.handoff_id, status).subscribe({
      next: () => { this.toast.success(status === 'claimed' ? 'Claimed. It is yours.' : 'Marked resolved.'); this.load(); },
      error: () => this.toast.error('Could not update this escalation.'),
    });
  }

  why(r: string): string { return reasonLabel(r); }
  isTicket(ref: string): boolean { return /^TK\d+$/.test(ref); }
  statusWord(s: string): string { return refLabel('escalation_status', s); }
}
