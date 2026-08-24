import { Component, OnDestroy, OnInit } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { CommonModule } from '@angular/common';
import { Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { SampleService, ReplayResult } from '../../services/sample.service';

@Component({
  selector: 'app-replay',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './replay.component.html',
  styleUrl: './replay.component.scss',
})
export class ReplayComponent implements OnInit, OnDestroy {
  traceId = '';
  result: ReplayResult | null = null;
  loading = true;
  error = '';

  private destroy$ = new Subject<void>();

  constructor(
    private route: ActivatedRoute,
    private sampleService: SampleService,
  ) {}

  ngOnInit(): void {
    this.traceId = this.route.snapshot.paramMap.get('traceId') ?? '';
    if (!this.traceId) {
      this.error = 'No trace ID provided.';
      this.loading = false;
      return;
    }
    this.sampleService
      .replayTrace(this.traceId)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (data) => {
          this.result = data;
          this.loading = false;
        },
        error: (err) => {
          this.error = err?.error?.detail ?? 'Replay failed — ensure the API is running.';
          this.loading = false;
        },
      });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  shortId(id: string): string {
    return id.slice(0, 8) + '…';
  }
}
