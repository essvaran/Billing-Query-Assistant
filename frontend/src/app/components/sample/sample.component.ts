import { Component, OnDestroy, OnInit } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { CommonModule } from '@angular/common';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { SampleService, TracePrompt, TraceRecord } from '../../services/sample.service';

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
  prompts: Record<string, TracePrompt> = {};
  promptLoading: Record<string, boolean> = {};

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

  loadPrompt(traceId: string): void {
    if (this.prompts[traceId] || this.promptLoading[traceId]) return;
    this.promptLoading[traceId] = true;
    this.sampleService
      .getPrompt(traceId)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (p) => { this.prompts[traceId] = p; this.promptLoading[traceId] = false; },
        error: () => { this.promptLoading[traceId] = false; },
      });
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

  queryTypeTitle(qt: string | null): string {
    const map: Record<string, string> = {
      'simple':        'Single direct question — one clear answer expected',
      'multi-part':    'Two or more sub-questions combined in one query',
      'exact keyword': 'Uses specific codes or technical terms (e.g. HC-BILL-001)',
      'semantic':      'Meaning-based query — intent must be inferred from natural language',
    };
    return qt ? (map[qt] ?? qt) : '';
  }
}
