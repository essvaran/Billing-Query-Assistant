import { Component, OnInit } from '@angular/core';
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
}

const SAMPLE_API = '/api/traces/sample';

const REFUSAL_PREFIX = 'I cannot answer that from the indexed help';
const EN_DASH_RE = /HC-BILL-\d+[–—]/;

function classifyMode(raw: string): string {
  const isRefusal = raw.trimStart().startsWith(REFUSAL_PREFIX);
  if (isRefusal) return 'Corpus Gap / False Refusal';
  if (EN_DASH_RE.test(raw)) return 'Citation Character Error';
  return 'Citation Abbreviation';
}

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

  readonly modeDetails: Record<string, string> = {
    'False Refusal': 'Correct chunk retrieved but model refused due to context noise or multi-part query sensitivity.',
    'Corpus Gap': 'The answer simply does not exist in any indexed document. Retrieval cannot fix this — new content must be authored.',
    'Citation Abbreviation': 'Model produced a correct answer but shortened chunk IDs; exact-match validator rejects abbreviated IDs.',
    'Citation Character Error': 'Model used en-dash (–) instead of double hyphen (--) as chunk ID separator; one-character difference breaks validation.',
    'Corpus Gap / False Refusal': 'Model refused — either the document is missing from the corpus entirely, or context noise caused an unnecessary refusal.',
  };

  readonly severityMap: Record<string, 'High' | 'Medium' | 'Low'> = {
    'False Refusal': 'Medium',
    'Corpus Gap': 'High',
    'Citation Abbreviation': 'Medium',
    'Citation Character Error': 'Low',
    'Corpus Gap / False Refusal': 'High',
  };

  constructor(private http: HttpClient) {}

  ngOnInit(): void {
    this.http.get<any[]>(SAMPLE_API).subscribe({
      next: (traces) => {
        const failed = traces.filter((t) => !t.citations_valid);
        const total = failed.length;

        const modeCounts: Record<string, number> = {};
        const modeTraces: Record<string, typeof failed> = {};

        for (const t of failed) {
          const mode = classifyMode(t.raw_output ?? '');
          modeCounts[mode] = (modeCounts[mode] ?? 0) + 1;
          if (!modeTraces[mode]) modeTraces[mode] = [];
          modeTraces[mode].push(t);
        }

        this.rows = failed.map((t) => {
          const mode = classifyMode(t.raw_output ?? '');
          const count = modeCounts[mode];
          const freq = total > 0 ? Math.round((count / total) * 100) + '%' : '—';
          const sev = this.severityMap[mode] ?? 'Medium';
          return {
            traceId: t.trace_id,
            shortId: (t.trace_id ?? '').slice(0, 8),
            question: t.question ?? '',
            mode,
            count,
            freq,
            severity: sev,
          };
        });

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
    return this.modeDetails[mode] ?? mode;
  }
}
