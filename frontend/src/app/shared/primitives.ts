import { ChangeDetectionStrategy, Component, EventEmitter, Input, Output } from '@angular/core';
import { PolicyVersion, TicketAnswer, TicketStatus } from '../services/tier1.service';
import { policyLabel, reasonLabel, statusLabel } from './labels';
import { refMeta } from './ref-data';

/** Status as text plus a dot: colour is never the only signal. */
@Component({
  selector: 'app-status-chip',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="chip" [attr.data-tone]="tone"><span class="dot" aria-hidden="true"></span>{{ label }}</span>`,
  styles: [`
    .chip { display: inline-flex; align-items: center; gap: .4rem; padding: .15rem .55rem; border-radius: 999px;
      font-size: .75rem; font-weight: 600; white-space: nowrap; background: var(--chip-bg); color: var(--chip-fg); }
    .dot { width: .5rem; height: .5rem; border-radius: 50%; background: currentColor; }
    [data-tone='muted']   { --chip-bg: rgba(108,112,134,.2); --chip-fg: var(--text-secondary); }
    [data-tone='accent']  { --chip-bg: rgba(137,180,250,.16); --chip-fg: var(--accent); }
    [data-tone='success'] { --chip-bg: rgba(166,227,161,.16); --chip-fg: var(--success); }
    [data-tone='warning'] { --chip-bg: rgba(250,179,135,.16); --chip-fg: var(--warning); }
    [data-tone='danger']  { --chip-bg: rgba(243,139,168,.16); --chip-fg: var(--danger); }
  `],
})
export class StatusChipComponent {
  @Input({ required: true }) status!: TicketStatus;
  get label(): string { return statusLabel(this.status); }
  get tone(): string {
    return { new: 'muted', draft_ready: 'accent', escalated_by_ai: 'warning', approved: 'success',
             escalated: 'warning', rejected: 'danger' }[this.status] ?? 'muted';
  }
}

@Component({
  selector: 'app-policy-badge',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="badge" [attr.data-v]="version" [title]="tip">{{ label }}</span>`,
  styles: [`
    .badge { display: inline-block; padding: .15rem .55rem; border-radius: var(--radius-sm); font-size: .75rem;
      font-weight: 700; white-space: nowrap; border: 1px solid transparent; }
    [data-v='refund-30d'] { color: var(--success); background: rgba(166,227,161,.12); border-color: rgba(166,227,161,.35); }
    [data-v='refund-14d'] { color: var(--warning); background: rgba(250,179,135,.12); border-color: rgba(250,179,135,.35); }
    [data-v='none'] { color: var(--text-muted); background: rgba(108,112,134,.15); }
  `],
})
export class PolicyBadgeComponent {
  @Input({ required: true }) version!: PolicyVersion | null;
  get label(): string { return policyLabel(this.version); }
  get tip(): string { return refMeta<string>('policy_version', this.version || 'none', 'tooltip') ?? ''; }
  get retired(): boolean { return !!refMeta<boolean>('policy_version', this.version, 'retired'); }
}

@Component({
  selector: 'app-kpi-tile',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="tile" [class.tile--unmeasured]="unmeasured">
      <div class="tile__label">{{ label }}</div>
      <div class="tile__value" [attr.data-tone]="tone">{{ value }}</div>
      @if (hint) { <div class="tile__hint">{{ hint }}</div> }
    </div>`,
  styles: [`
    .tile { background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-lg);
      padding: .9rem 1rem; min-width: 0; }
    .tile__label { font-size: .72rem; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--text-muted); }
    .tile__value { font-size: 1.55rem; font-weight: 700; margin-top: .25rem; color: var(--text-primary); overflow-wrap: anywhere; }
    .tile--unmeasured .tile__value { font-size: 1rem; font-weight: 600; color: var(--text-muted); padding: .35rem 0; }
    [data-tone='good'] { color: var(--success); } [data-tone='bad'] { color: var(--danger); } [data-tone='warn'] { color: var(--warning); }
    .tile__hint { font-size: .75rem; color: var(--text-muted); margin-top: .2rem; line-height: 1.4; }
  `],
})
export class KpiTileComponent {
  @Input({ required: true }) label!: string;
  @Input({ required: true }) value!: string;
  @Input() hint = '';
  @Input() tone: '' | 'good' | 'bad' | 'warn' = '';
  get unmeasured(): boolean { return this.value === 'Not measured'; }
}

@Component({
  selector: 'app-empty-state',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="empty" role="status">
      <div class="empty__title">{{ title }}</div>
      @if (detail) { <p class="empty__detail">{{ detail }}</p> }
      <ng-content />
    </div>`,
  styles: [`
    .empty { text-align: center; padding: 2.5rem 1rem; color: var(--text-secondary); }
    .empty__title { font-weight: 600; color: var(--text-primary); margin-bottom: .35rem; }
    .empty__detail { font-size: .85rem; max-width: 36rem; margin: 0 auto .75rem; }
  `],
})
export class EmptyStateComponent {
  @Input({ required: true }) title!: string;
  @Input() detail = '';
}

/** Every failure says what happened, gives the trace id when there is one, and offers a next step. */
@Component({
  selector: 'app-error-state',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="error" role="alert">
      <div class="error__title">{{ title }}</div>
      <p class="error__detail">{{ message }}</p>
      @if (traceId) { <p class="error__trace">Trace <code>{{ traceId }}</code></p> }
      <div class="error__actions">
        @if (retryLabel) { <button type="button" class="t1-btn" (click)="retry.emit()">{{ retryLabel }}</button> }
        <ng-content />
      </div>
    </div>`,
  styles: [`
    .error { border: 1px solid rgba(243,139,168,.4); background: rgba(243,139,168,.08); border-radius: var(--radius-lg);
      padding: 1rem 1.1rem; }
    .error__title { font-weight: 700; color: var(--danger); }
    .error__detail { margin: .3rem 0 .6rem; font-size: .88rem; color: var(--text-secondary); }
    .error__trace { font-size: .75rem; color: var(--text-muted); margin-bottom: .6rem; }
    .error__actions { display: flex; gap: .5rem; flex-wrap: wrap; }
  `],
})
export class ErrorStateComponent {
  @Input() title = 'Something went wrong';
  @Input({ required: true }) message!: string;
  @Input() traceId = '';
  @Input() retryLabel = '';
  @Output() retry = new EventEmitter<void>();
}

/** Says in one line whether the draft is ready to send or why a person should take over. */
@Component({
  selector: 'app-decision-banner',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="banner" [attr.data-tone]="tone" role="status">
      <strong>{{ headline }}</strong>
      @if (detail) { <span class="banner__detail">{{ detail }}</span> }
    </div>`,
  styles: [`
    .banner { display: flex; flex-wrap: wrap; gap: .25rem .75rem; align-items: baseline; padding: .65rem .9rem;
      border-radius: var(--radius-md); border: 1px solid transparent; font-size: .88rem; }
    .banner__detail { color: var(--text-secondary); font-size: .82rem; }
    [data-tone='ready'] { background: rgba(166,227,161,.1); border-color: rgba(166,227,161,.35); }
    [data-tone='ready'] strong { color: var(--success); }
    [data-tone='escalate'] { background: rgba(250,179,135,.1); border-color: rgba(250,179,135,.4); }
    [data-tone='escalate'] strong { color: var(--warning); }
  `],
})
export class DecisionBannerComponent {
  @Input({ required: true }) result!: TicketAnswer;
  get tone(): string { return this.result.decision === 'ANSWER' ? 'ready' : 'escalate'; }
  get headline(): string {
    return this.result.decision === 'ANSWER' ? 'Draft ready for your review' : 'Escalation recommended';
  }
  get detail(): string {
    if (this.result.decision === 'ANSWER') return 'Check the sources, then approve or edit.';
    const why = reasonLabel(this.result.reason);
    return this.result.handoff_id ? `${why}. A handoff was created for a person.` : why;
  }
}
