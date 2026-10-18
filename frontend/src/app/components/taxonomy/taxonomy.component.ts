import { Component, OnInit } from '@angular/core';
import { refDescription, refLabel, refMeta } from '../../shared/ref-data';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { HttpClient } from '@angular/common/http';

interface TaxonomyRow {
  traceId: string;
  shortId: string;
  question: string;
  mode: string;
  count: number;
  freq: string;
  severity: 'High' | 'Medium' | 'Low';
  code: string;
}

const TAXONOMY_API = '/api/traces/sample/taxonomy';

@Component({
  selector: 'app-taxonomy',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './taxonomy.component.html',
  styleUrl: './taxonomy.component.scss',
})
export class TaxonomyComponent implements OnInit {
  rows: TaxonomyRow[] = [];
  loading = true;
  error = '';

  total = 0;
  failedCount = 0;
  seed: number | null = null;

  constructor(private http: HttpClient) {}

  ngOnInit(): void {
    this.http.get<{ seed: number }>('/api/traces/sample/meta').subscribe({ next: m => (this.seed = m.seed), error: () => {} });
    this.http.get<{ total: number; failed: number; rows: { trace_id: string; question: string; mode: string }[] }>(TAXONOMY_API).subscribe({
      next: (data) => {
        this.total = data.total;
        this.failedCount = data.failed;
        const counts: Record<string, number> = {};
        for (const r of data.rows) counts[r.mode] = (counts[r.mode] ?? 0) + 1;
        this.rows = data.rows.map((t) => ({
          traceId: t.trace_id,
          shortId: (t.trace_id ?? '').slice(0, 8),
          question: t.question ?? '',
          mode: refLabel('sample_failure_mode', t.mode),
          count: counts[t.mode],
          freq: data.failed > 0 ? Math.round((counts[t.mode] / data.failed) * 100) + '%' : '-',
          severity: (refMeta<string>('sample_failure_mode', t.mode, 'severity') ?? 'Medium') as 'High' | 'Medium' | 'Low',
          code: t.mode,
        }));
        this.loading = false;
      },
      error: (err) => {
        this.error = `Failed to load sample: ${err.message ?? err}`;
        this.loading = false;
      },
    });
  }

  severityClass(sev: string): string {
    return `sev--${sev.toLowerCase()}`;
  }

  modeDetail(mode: string): string {
    const row = this.rows.find(r => r.mode === mode);
    return refDescription('sample_failure_mode', row?.code ?? mode) || mode;
  }
}
