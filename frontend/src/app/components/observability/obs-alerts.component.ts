import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, takeUntil } from 'rxjs';
import { AlertConfig, AlertRow, ObservabilityService, apiError } from '../../services/observability.service';
import { fmtUsd, fmtUtc, shortId } from './obs-format';

@Component({
  selector: 'app-obs-alerts',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './obs-alerts.component.html',
  styleUrl: './obs-shared.scss',
})
export class ObsAlertsComponent implements OnInit, OnDestroy {
  private api = inject(ObservabilityService);
  private destroy$ = new Subject<void>();

  readonly fmtUtc = fmtUtc;
  readonly fmtUsd = fmtUsd;
  readonly shortId = shortId;

  config: AlertConfig | null = null;
  rows: AlertRow[] = [];
  statusFilter = '';
  error: string | null = null;
  loading = false;

  testing = false;
  testResult: { ok: boolean; text: string } | null = null;

  ngOnInit(): void {
    this.loadConfig();
    this.loadHistory();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  private loadConfig(): void {
    this.api
      .alertConfig()
      .pipe(takeUntil(this.destroy$))
      .subscribe({ next: this.onConfig.bind(this), error: this.onError.bind(this) });
  }

  private onConfig(c: AlertConfig): void {
    this.config = c;
  }

  loadHistory(): void {
    this.loading = true;
    this.api
      .alerts(this.statusFilter || undefined)
      .pipe(takeUntil(this.destroy$))
      .subscribe({ next: this.onHistory.bind(this), error: this.onError.bind(this) });
  }

  private onHistory(rows: AlertRow[]): void {
    this.rows = rows;
    this.loading = false;
  }

  private onError(err: unknown): void {
    this.loading = false;
    this.error = apiError(err);
  }

  sendTest(): void {
    this.testing = true;
    this.testResult = null;
    this.api
      .testAlert()
      .pipe(takeUntil(this.destroy$))
      .subscribe({ next: this.onTest.bind(this), error: this.onTestError.bind(this) });
  }

  private onTest(r: { ok: boolean; message: string }): void {
    this.testing = false;
    this.testResult = { ok: r.ok, text: r.message };
    this.loadHistory();
  }

  private onTestError(err: unknown): void {
    this.testing = false;
    this.testResult = { ok: false, text: apiError(err) };
  }

  statusClass(status: string): string {
    switch (status) {
      case 'sent':
        return 'badge--green';
      case 'test':
        return 'badge--blue';
      case 'failed':
        return 'badge--red';
      default:
        return 'badge--amber';
    }
  }
}
