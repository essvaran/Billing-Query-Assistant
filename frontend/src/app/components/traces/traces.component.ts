import { Component, OnInit, OnDestroy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, debounceTime, distinctUntilChanged, takeUntil } from 'rxjs';
import {
  TracesService,
  TraceRecord,
  TraceFilters,
} from '../../services/traces.service';

@Component({
  selector: 'app-traces',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './traces.component.html',
  styleUrl: './traces.component.scss',
})
export class TracesComponent implements OnInit, OnDestroy {
  private tracesService = inject(TracesService);
  private destroy$ = new Subject<void>();
  private questionSearch$ = new Subject<string>();

  traces: TraceRecord[] = [];
  total = 0;
  loading = false;
  error: string | null = null;

  // Filters
  questionFilter = '';
  citationsValidFilter: 'all' | 'true' | 'false' = 'all';
  retrieverFilter = 'all';
  errorOnly = false;

  // Pagination
  readonly pageSize = 10;
  offset = 0;

  // Expand state per trace
  expanded: Record<string, boolean> = {};

  get totalPages(): number {
    return Math.ceil(this.total / this.pageSize);
  }

  get currentPage(): number {
    return Math.floor(this.offset / this.pageSize) + 1;
  }

  ngOnInit(): void {
    this.questionSearch$
      .pipe(debounceTime(300), distinctUntilChanged(), takeUntil(this.destroy$))
      .subscribe(() => {
        this.offset = 0;
        this.fetchTraces();
      });
    this.fetchTraces();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  onQuestionInput(value: string): void {
    this.questionFilter = value;
    this.questionSearch$.next(value);
  }

  onFilterChange(): void {
    this.offset = 0;
    this.fetchTraces();
  }

  nextPage(): void {
    if (this.offset + this.pageSize < this.total) {
      this.offset += this.pageSize;
      this.fetchTraces();
    }
  }

  prevPage(): void {
    if (this.offset > 0) {
      this.offset = Math.max(0, this.offset - this.pageSize);
      this.fetchTraces();
    }
  }

  toggleExpand(traceId: string): void {
    this.expanded[traceId] = !this.expanded[traceId];
  }

  isExpanded(traceId: string): boolean {
    return !!this.expanded[traceId];
  }

  formatTimestamp(ts: string): string {
    try {
      return new Date(ts).toLocaleString();
    } catch {
      return ts;
    }
  }

  shortId(id: string): string {
    return id.slice(0, 8) + '…';
  }

  private fetchTraces(): void {
    this.loading = true;
    this.error = null;

    const filters: TraceFilters = {
      limit: this.pageSize,
      offset: this.offset,
      error_only: this.errorOnly,
    };
    if (this.questionFilter.trim()) {
      filters.question = this.questionFilter.trim();
    }
    if (this.citationsValidFilter !== 'all') {
      filters.citations_valid = this.citationsValidFilter === 'true';
    }
    if (this.retrieverFilter !== 'all') {
      filters.retriever = this.retrieverFilter;
    }

    this.tracesService
      .getTraces(filters)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (resp) => {
          this.traces = resp.traces;
          this.total = resp.total;
          this.loading = false;
        },
        error: (err) => {
          this.error = err?.message ?? 'Failed to load traces.';
          this.loading = false;
        },
      });
  }
}
