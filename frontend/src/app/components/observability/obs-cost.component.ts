import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { refValues } from '../../shared/ref-data';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, debounceTime, takeUntil } from 'rxjs';
import { GroupStats, ObservabilityService, Stats, TenX, apiError } from '../../services/observability.service';
import { fmtMs, fmtUsd } from './obs-format';

@Component({
  selector: 'app-obs-cost',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './obs-cost.component.html',
  styleUrl: './obs-shared.scss',
})
export class ObsCostComponent implements OnInit, OnDestroy {
  private api = inject(ObservabilityService);
  private destroy$ = new Subject<void>();
  private tenxInput$ = new Subject<void>();

  readonly fmtUsd = fmtUsd;
  readonly fmtMs = fmtMs;
  get windows(): number[] { return refValues('obs_window').map(v => Number(v.meta['days'])); }

  days = 90;
  stats: Stats | null = null;
  error: string | null = null;
  loading = false;

  baselineRpm: number | null = null;
  multiplier: number | null = null;
  tenx: TenX | null = null;
  tenxError: string | null = null;

  ngOnInit(): void {
    this.tenxInput$.pipe(debounceTime(300), takeUntil(this.destroy$)).subscribe({ next: this.loadTenx.bind(this) });
    this.api.meta().pipe(takeUntil(this.destroy$)).subscribe({
      next: m => { this.baselineRpm = m.tenx_baseline_rpm; this.multiplier = m.tenx_multiplier; this.loadTenx(); },
      error: () => {},
    });
    this.load();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  load(): void {
    this.loading = true;
    this.error = null;
    this.api
      .stats(this.days)
      .pipe(takeUntil(this.destroy$))
      .subscribe({ next: this.onStats.bind(this), error: this.onStatsError.bind(this) });
  }

  private onStats(s: Stats): void {
    this.stats = s;
    this.loading = false;
    this.loadTenx();
  }

  private onStatsError(err: unknown): void {
    this.loading = false;
    this.error = apiError(err);
  }

  onTenxInput(): void {
    this.tenxInput$.next();
  }

  private loadTenx(): void {
    if (this.baselineRpm === null || this.multiplier === null) return;
    const rpm = Number(this.baselineRpm);
    const mult = Number(this.multiplier);
    if (!(rpm > 0) || !(mult >= 1)) {
      this.tenxError = 'Baseline must be above 0 and the multiplier at least 1.';
      return;
    }
    this.tenxError = null;
    this.api
      .tenx(rpm, mult)
      .pipe(takeUntil(this.destroy$))
      .subscribe({ next: this.onTenx.bind(this), error: this.onTenxError.bind(this) });
  }

  private onTenx(t: TenX): void {
    this.tenx = t;
  }

  private onTenxError(err: unknown): void {
    this.tenxError = apiError(err);
  }

  /** Percent change of average cost versus the previous version in the list. */
  delta(index: number): number | null {
    if (!this.stats || index === 0) {
      return null;
    }
    const prev = this.stats.by_prompt_version[index - 1];
    const cur = this.stats.by_prompt_version[index];
    if (!prev.avg_cost_usd) {
      return null;
    }
    return ((cur.avg_cost_usd - prev.avg_cost_usd) / prev.avg_cost_usd) * 100;
  }

  unverifiedRate(g: GroupStats): string {
    return g.llm_requests ? ((g.unverified_answers / g.llm_requests) * 100).toFixed(1) + '%' : '-';
  }
}
