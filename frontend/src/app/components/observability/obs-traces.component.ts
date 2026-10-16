import { Component, EventEmitter, HostListener, Input, OnDestroy, OnInit, Output, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, takeUntil } from 'rxjs';
import {
  DrillRow,
  ObservabilityService,
  TraceDetail,
  TraceFilter,
  TraceList,
  apiError,
} from '../../services/observability.service';
import { fmtMs, fmtUsd, fmtUtc, mmss, shortId, utcInputToIso, yesterdayWindowUtc } from './obs-format';

interface Notice {
  kind: 'ok' | 'err' | 'warn';
  text: string;
}

@Component({
  selector: 'app-obs-traces',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './obs-traces.component.html',
  styleUrl: './obs-shared.scss',
})
export class ObsTracesComponent implements OnInit, OnDestroy {
  private api = inject(ObservabilityService);
  private destroy$ = new Subject<void>();

  @Input() demoTools = false;
  @Input() drillBarSeconds = 300;
  @Input() initialTraceId: string | null = null;
  @Output() openEval = new EventEmitter<void>();

  readonly pageSize = 15;
  readonly fmtMs = fmtMs;
  readonly fmtUsd = fmtUsd;
  readonly fmtUtc = fmtUtc;
  readonly mmss = mmss;
  readonly shortId = shortId;

  // filters (date-time boxes are interpreted as UTC)
  after = '';
  before = '';
  keyword = '';
  promptVersion = '';
  costAbove: number | null = null;
  unverified = false;
  errorsOnly = false;
  userFilter = '';

  list: TraceList | null = null;
  offset = 0;
  loading = false;
  notice: Notice | null = null;

  // detail drawer
  detail: TraceDetail | null = null;
  detailLoading = false;
  caseExpected = 'refusal';
  caseMode = 'corpus_gap';
  caseNotes = '';
  caseBusy = false;
  caseNotice: Notice | null = null;

  // support drill
  drillRunning = false;
  drillStartedAt = 0;
  drillElapsed = 0;
  drillResult: { seconds: number; passed: boolean; slice: string; traceId: string } | null = null;
  drillBusy = false;
  drills: DrillRow[] = [];
  private timer: ReturnType<typeof setInterval> | null = null;

  get totalPages(): number {
    return this.list ? Math.max(1, Math.ceil(this.list.total / this.pageSize)) : 1;
  }

  get currentPage(): number {
    return Math.floor(this.offset / this.pageSize) + 1;
  }

  ngOnInit(): void {
    this.search();
    this.loadDrills();
    if (this.initialTraceId) {
      this.open(this.initialTraceId);
    }
  }

  ngOnDestroy(): void {
    this.stopTimer();
    this.destroy$.next();
    this.destroy$.complete();
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.closeDetail();
  }

  // ------------------------------------------------------------ search

  private currentFilter(): TraceFilter {
    return {
      after: utcInputToIso(this.after),
      before: utcInputToIso(this.before),
      keyword: this.keyword.trim() || undefined,
      prompt_version: this.promptVersion.trim() || undefined,
      cost_above: this.costAbove,
      unverified: this.unverified,
      errors_only: this.errorsOnly,
      user: this.userFilter.trim() || undefined,
      limit: this.pageSize,
      offset: this.offset,
    };
  }

  search(): void {
    this.offset = 0;
    this.fetch();
  }

  private fetch(): void {
    this.loading = true;
    this.notice = null;
    this.api
      .traces(this.currentFilter())
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: this.onList.bind(this),
        error: this.onListError.bind(this),
      });
  }

  private onList(result: TraceList): void {
    this.list = result;
    this.loading = false;
  }

  private onListError(err: unknown): void {
    this.loading = false;
    this.notice = { kind: 'err', text: apiError(err) };
  }

  reset(): void {
    this.after = '';
    this.before = '';
    this.keyword = '';
    this.promptVersion = '';
    this.costAbove = null;
    this.unverified = false;
    this.errorsOnly = false;
    this.userFilter = '';
    this.search();
  }

  presetYesterday(): void {
    const w = yesterdayWindowUtc();
    this.after = w.after;
    this.before = w.before;
    this.search();
  }

  nextPage(): void {
    if (this.list && this.offset + this.pageSize < this.list.total) {
      this.offset += this.pageSize;
      this.fetch();
    }
  }

  prevPage(): void {
    if (this.offset > 0) {
      this.offset = Math.max(0, this.offset - this.pageSize);
      this.fetch();
    }
  }

  private sliceDescription(): string {
    const parts: string[] = [];
    if (this.after || this.before) {
      parts.push('time window');
    }
    if (this.keyword.trim()) {
      parts.push('keyword "' + this.keyword.trim() + '"');
    }
    if (this.promptVersion.trim()) {
      parts.push('prompt version ' + this.promptVersion.trim());
    }
    if (this.costAbove !== null && this.costAbove !== undefined) {
      parts.push('cost outlier');
    }
    if (this.unverified) {
      parts.push('unverified answers');
    }
    if (this.userFilter.trim()) {
      parts.push('user ' + this.userFilter.trim());
    }
    return parts.length ? parts.join(' + ') : 'no filter (browsed the list)';
  }

  // ------------------------------------------------------------ detail drawer

  open(traceId: string): void {
    this.detailLoading = true;
    this.detail = null;
    this.caseNotice = null;
    this.api
      .trace(traceId)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: this.onDetail.bind(this),
        error: this.onDetailError.bind(this),
      });
  }

  private onDetail(d: TraceDetail): void {
    this.detail = d;
    this.detailLoading = false;
    this.caseExpected = d.is_refusal ? 'answer' : 'refusal';
    this.caseMode = this.caseExpected === 'refusal' ? 'corpus_gap' : 'false_refusal';
    this.caseNotes = '';
  }

  private onDetailError(err: unknown): void {
    this.detailLoading = false;
    this.notice = { kind: 'err', text: apiError(err) };
  }

  closeDetail(): void {
    this.detail = null;
    this.detailLoading = false;
  }

  onExpectedChange(): void {
    this.caseMode = this.caseExpected === 'refusal' ? 'corpus_gap' : 'false_refusal';
  }

  spanWidth(latency: number | null): number {
    if (!this.detail || latency === null) {
      return 0;
    }
    const total = (this.detail.spans[1].latency_ms || 0) + (this.detail.spans[2].latency_ms || 0);
    return total > 0 ? Math.max(2, Math.round((latency / total) * 100)) : 0;
  }

  createCase(): void {
    if (!this.detail) {
      return;
    }
    this.caseBusy = true;
    this.caseNotice = null;
    this.api
      .createEvalCase(this.detail.trace_id, {
        expected_behavior: this.caseExpected,
        mode: this.caseMode,
        notes: this.caseNotes,
      })
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: this.onCaseCreated.bind(this),
        error: this.onCaseError.bind(this),
      });
  }

  private onCaseCreated(created: { case_id: string }): void {
    this.caseBusy = false;
    if (this.detail) {
      this.detail.eval_case_id = created.case_id;
    }
    this.caseNotice = { kind: 'ok', text: 'Eval case ' + created.case_id + ' created and added to the eval set.' };
  }

  private onCaseError(err: unknown): void {
    this.caseBusy = false;
    this.caseNotice = { kind: 'err', text: apiError(err) };
  }

  // ------------------------------------------------------------ support drill

  startDrill(): void {
    this.drillResult = null;
    this.drillRunning = true;
    this.drillStartedAt = Date.now();
    this.drillElapsed = 0;
    this.stopTimer();
    this.timer = setInterval(this.tick.bind(this), 250);
  }

  cancelDrill(): void {
    this.drillRunning = false;
    this.stopTimer();
  }

  private tick(): void {
    this.drillElapsed = (Date.now() - this.drillStartedAt) / 1000;
  }

  private stopTimer(): void {
    if (this.timer !== null) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  markFound(): void {
    if (!this.detail || !this.drillRunning) {
      return;
    }
    this.tick();
    const seconds = this.drillElapsed;
    const slice = this.sliceDescription();
    const traceId = this.detail.trace_id;
    this.drillRunning = false;
    this.stopTimer();
    this.drillBusy = true;
    this.api
      .recordDrill({ trace_id: traceId, seconds: seconds, slice: slice, notes: '' })
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: this.onDrillSaved.bind(this, seconds, slice, traceId),
        error: this.onDrillError.bind(this),
      });
  }

  private onDrillSaved(seconds: number, slice: string, traceId: string, saved: { passed_bar: boolean }): void {
    this.drillBusy = false;
    this.drillResult = { seconds: seconds, passed: saved.passed_bar, slice: slice, traceId: traceId };
    this.loadDrills();
  }

  private onDrillError(err: unknown): void {
    this.drillBusy = false;
    this.notice = { kind: 'err', text: 'Could not save the drill: ' + apiError(err) };
  }

  private loadDrills(): void {
    this.api
      .drills()
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: this.onDrills.bind(this),
        error: this.onDrillsError.bind(this),
      });
  }

  private onDrills(rows: DrillRow[]): void {
    this.drills = rows;
  }

  private onDrillsError(): void {
    this.drills = [];
  }

  plant(): void {
    this.api
      .plantDemo()
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: this.onPlanted.bind(this),
        error: this.onListError.bind(this),
      });
  }

  private onPlanted(): void {
    this.keyword = '';
    this.after = '';
    this.before = '';
    this.unverified = false;
    this.fetch();
    this.notice = {
      kind: 'warn',
      text: 'A bad refund answer from yesterday afternoon was planted. Start the drill and find it without looking at the list order.',
    };
  }
}
