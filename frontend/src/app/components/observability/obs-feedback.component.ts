import { Component, EventEmitter, OnDestroy, OnInit, Output, inject } from '@angular/core';
import { refValues } from '../../shared/ref-data';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, takeUntil } from 'rxjs';
import { FeedbackItem, FeedbackList, ObservabilityService, apiError } from '../../services/observability.service';
import { fmtUtc, shortId } from './obs-format';

@Component({
  selector: 'app-obs-feedback',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './obs-feedback.component.html',
  styleUrl: './obs-shared.scss',
})
export class ObsFeedbackComponent implements OnInit, OnDestroy {
  refValues = refValues;
  private api = inject(ObservabilityService);
  private destroy$ = new Subject<void>();

  @Output() openTrace = new EventEmitter<string>();
  @Output() changed = new EventEmitter<void>();

  readonly fmtUtc = fmtUtc;
  readonly shortId = shortId;
  readonly pageSize = 15;

  rating = 'down';
  status = 'new';
  offset = 0;
  list: FeedbackList | null = null;
  loading = false;
  error: string | null = null;

  /** Row being reviewed (inline note box) and its note text. */
  reviewingId: number | null = null;
  note = '';
  busyId: number | null = null;

  get totalPages(): number {
    return this.list ? Math.max(1, Math.ceil(this.list.total / this.pageSize)) : 1;
  }

  get currentPage(): number {
    return Math.floor(this.offset / this.pageSize) + 1;
  }

  ngOnInit(): void {
    this.load();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  filterChanged(): void {
    this.offset = 0;
    this.load();
  }

  load(): void {
    this.loading = true;
    this.error = null;
    this.api
      .feedback({ rating: this.rating, status: this.status, limit: this.pageSize, offset: this.offset })
      .pipe(takeUntil(this.destroy$))
      .subscribe({ next: this.onList.bind(this), error: this.onError.bind(this) });
  }

  private onList(result: FeedbackList): void {
    this.list = result;
    this.loading = false;
  }

  private onError(err: unknown): void {
    this.loading = false;
    this.busyId = null;
    this.error = apiError(err);
  }

  nextPage(): void {
    if (this.list && this.offset + this.pageSize < this.list.total) {
      this.offset += this.pageSize;
      this.load();
    }
  }

  prevPage(): void {
    if (this.offset > 0) {
      this.offset = Math.max(0, this.offset - this.pageSize);
      this.load();
    }
  }

  startReview(item: FeedbackItem): void {
    this.reviewingId = item.id;
    this.note = item.admin_note || '';
  }

  cancelReview(): void {
    this.reviewingId = null;
    this.note = '';
  }

  markReviewed(item: FeedbackItem): void {
    this.setStatus(item, 'reviewed', this.note);
  }

  reopen(item: FeedbackItem): void {
    this.setStatus(item, 'new', '');
  }

  private setStatus(item: FeedbackItem, status: 'new' | 'reviewed', note: string): void {
    this.busyId = item.id;
    this.api
      .reviewFeedback(item.id, status, note)
      .pipe(takeUntil(this.destroy$))
      .subscribe({ next: this.onReviewed.bind(this), error: this.onError.bind(this) });
  }

  private onReviewed(): void {
    this.busyId = null;
    this.reviewingId = null;
    this.note = '';
    this.changed.emit();
    this.load();
  }
}
