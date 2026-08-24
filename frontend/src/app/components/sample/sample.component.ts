import { Component, OnDestroy, OnInit } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { CommonModule } from '@angular/common';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { SampleService, TraceRecord } from '../../services/sample.service';

@Component({
  selector: 'app-sample',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './sample.component.html',
  styleUrl: './sample.component.scss',
})
export class SampleComponent implements OnInit, OnDestroy {
  traces: TraceRecord[] = [];
  loading = true;
  error = '';
  expanded: Record<string, boolean> = {};

  private destroy$ = new Subject<void>();

  constructor(
    private sampleService: SampleService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.sampleService
      .getSample()
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (data) => {
          this.traces = data;
          this.loading = false;
        },
        error: (err) => {
          this.error = err?.error?.detail ?? 'Failed to load sample traces.';
          this.loading = false;
        },
      });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  toggleExpand(id: string): void {
    this.expanded[id] = !this.expanded[id];
  }

  isExpanded(id: string): boolean {
    return !!this.expanded[id];
  }

  goReplay(traceId: string): void {
    this.router.navigate(['/replay', traceId]);
  }

  shortId(id: string): string {
    return id.slice(0, 8) + '…';
  }

  formatTimestamp(ts: string): string {
    return new Date(ts).toLocaleString();
  }

  get validCount(): number {
    return this.traces.filter((t) => t.citations_valid).length;
  }

  get invalidCount(): number {
    return this.traces.filter((t) => !t.citations_valid).length;
  }
}
