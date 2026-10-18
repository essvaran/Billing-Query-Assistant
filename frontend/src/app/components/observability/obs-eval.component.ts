import { Component, ElementRef, OnDestroy, OnInit, inject } from '@angular/core';
import { refLabel } from '../../shared/ref-data';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, takeUntil } from 'rxjs';
import {
  EvalCase,
  EvalDiff,
  EvalResult,
  EvalRun,
  EvalRunDetail,
  ObservabilityService,
  apiError,
} from '../../services/observability.service';
import { fmtUtc, shortId } from './obs-format';

@Component({
  selector: 'app-obs-eval',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './obs-eval.component.html',
  styleUrl: './obs-shared.scss',
})
export class ObsEvalComponent implements OnInit, OnDestroy {
  private api = inject(ObservabilityService);
  private host = inject(ElementRef);
  private destroy$ = new Subject<void>();
  private poll: ReturnType<typeof setInterval> | null = null;

  readonly fmtUtc = fmtUtc;
  readonly shortId = shortId;

  cases: EvalCase[] = [];
  runs: EvalRun[] = [];
  error: string | null = null;
  info: string | null = null;

  runningCase: string | null = null;
  caseOutcome: (EvalResult & { run_id: string }) | null = null;
  startingSuite = false;

  selectedRun: EvalRunDetail | null = null;
  baseRunId = '';
  headRunId = '';
  diff: EvalDiff | null = null;
  diffBusy = false;

  get suiteRunning(): boolean {
    for (const r of this.runs) {
      if (r.status === 'running' && r.source.indexOf('ui') === 0) {
        return true;
      }
    }
    return false;
  }

  ngOnInit(): void {
    this.refreshAll();
    this.poll = setInterval(this.onPoll.bind(this), 3000);
  }

  ngOnDestroy(): void {
    if (this.poll !== null) {
      clearInterval(this.poll);
    }
    this.destroy$.next();
    this.destroy$.complete();
  }

  private onPoll(): void {
    if (this.suiteRunning) {
      this.loadRuns(true);
    }
  }

  refreshAll(): void {
    this.loadCases();
    this.loadRuns(false);
  }

  private loadCases(): void {
    this.api
      .evalCases()
      .pipe(takeUntil(this.destroy$))
      .subscribe({ next: this.onCases.bind(this), error: this.onError.bind(this) });
  }

  private onCases(cases: EvalCase[]): void {
    this.cases = cases;
  }

  private loadRuns(fromPoll: boolean): void {
    this.api
      .evalRuns()
      .pipe(takeUntil(this.destroy$))
      .subscribe({ next: this.onRuns.bind(this, fromPoll), error: this.onError.bind(this) });
  }

  private onRuns(fromPoll: boolean, runs: EvalRun[]): void {
    const wasRunning = this.suiteRunning;
    this.runs = runs;
    if (!this.baseRunId && !this.headRunId) {
      this.pickDefaultComparison();
    }
    if (fromPoll && wasRunning && !this.suiteRunning) {
      this.loadCases();
      this.info = 'The suite run finished.';
      if (this.runs.length > 0) {
        this.headRunId = this.runs[0].run_id;
      }
    }
    if (fromPoll && this.selectedRun) {
      this.refreshRun(this.selectedRun.run.run_id);
    }
  }

  private pickDefaultComparison(): void {
    const done: EvalRun[] = [];
    for (const r of this.runs) {
      if (r.status === 'done' && r.total > 1) {
        done.push(r);
      }
    }
    if (done.length >= 2) {
      this.headRunId = done[0].run_id;
      this.baseRunId = done[1].run_id;
    }
  }

  private onError(err: unknown): void {
    this.error = apiError(err);
    this.runningCase = null;
    this.startingSuite = false;
  }

  runLabel(r: EvalRun): string {
    return r.prompt_version + '  ' + r.passed + '/' + r.total + '  ' + fmtUtc(r.started_at);
  }

  isGreen(r: EvalRun): boolean {
    return r.status === 'done' && r.total > 0 && r.passed === r.total;
  }

  runCase(caseId: string): void {
    this.runningCase = caseId;
    this.error = null;
    this.caseOutcome = null;
    this.api
      .runCase(caseId)
      .pipe(takeUntil(this.destroy$))
      .subscribe({ next: this.onCaseRun.bind(this), error: this.onError.bind(this) });
  }

  private onCaseRun(result: EvalResult & { run_id: string }): void {
    this.runningCase = null;
    this.caseOutcome = result;
    this.refreshAll();
  }

  startSuite(): void {
    this.startingSuite = true;
    this.error = null;
    this.info = null;
    this.api
      .startSuite()
      .pipe(takeUntil(this.destroy$))
      .subscribe({ next: this.onSuiteStarted.bind(this), error: this.onError.bind(this) });
  }

  private onSuiteStarted(): void {
    this.startingSuite = false;
    this.info = 'Suite started. It runs in the background and calls the model once per case, so it can take a few minutes.';
    this.loadRuns(false);
  }

  openRun(runId: string): void {
    this.api
      .evalRun(runId)
      .pipe(takeUntil(this.destroy$))
      .subscribe({ next: this.onRunDetail.bind(this), error: this.onError.bind(this) });
  }

  private onRunDetail(detail: EvalRunDetail): void {
    this.selectedRun = detail;
    setTimeout(this.scrollToDetail.bind(this), 50);
  }

  private refreshRun(runId: string): void {
    this.api
      .evalRun(runId)
      .pipe(takeUntil(this.destroy$))
      .subscribe({ next: this.onRunRefreshed.bind(this), error: this.onError.bind(this) });
  }

  private onRunRefreshed(detail: EvalRunDetail): void {
    this.selectedRun = detail;
  }

  private scrollToDetail(): void {
    const target = (this.host.nativeElement as HTMLElement).querySelector('#detail-title');
    if (target) {
      target.scrollIntoView({ behavior: 'instant', block: 'start' });
    }
  }

  closeRun(): void {
    this.selectedRun = null;
  }

  compare(): void {
    if (!this.baseRunId || !this.headRunId) {
      return;
    }
    this.diffBusy = true;
    this.error = null;
    this.api
      .evalDiff(this.baseRunId, this.headRunId)
      .pipe(takeUntil(this.destroy$))
      .subscribe({ next: this.onDiff.bind(this), error: this.onDiffError.bind(this) });
  }

  private onDiff(d: EvalDiff): void {
    this.diffBusy = false;
    this.diff = d;
  }

  private onDiffError(err: unknown): void {
    this.diffBusy = false;
    this.error = apiError(err);
  }

  changeLabel(change: string): string { return refLabel('eval_change', change); }

  changeClass(change: string): string {
    switch (change) {
      case 'fixed':
        return 'badge--green';
      case 'regressed':
        return 'badge--red';
      case 'same_fail':
        return 'badge--amber';
      default:
        return '';
    }
  }

  passText(value: boolean | null): string {
    return value === null ? '-' : value ? 'pass' : 'FAIL';
  }
}
