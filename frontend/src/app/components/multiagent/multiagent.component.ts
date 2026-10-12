import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  AskResult,
  Handoff,
  MaCase,
  MaResults,
  MaStatus,
  MultiAgentService,
} from '../../services/multiagent.service';

interface MetricRow {
  label: string;
  single: string;
  multi: string;
  singleWins: boolean;
  multiWins: boolean;
}

interface ShareRow {
  name: string;
  tokens: number;
  share: number;
}

@Component({
  selector: 'app-multiagent',
  standalone: true,
  imports: [CommonModule, FormsModule, DatePipe],
  templateUrl: './multiagent.component.html',
  styleUrl: './multiagent.component.scss',
})
export class MultiAgentComponent implements OnInit, OnDestroy {
  cases: MaCase[] = [];
  results: MaResults | null = null;
  status: MaStatus = { status: 'idle', started_at: null, error: null, done: 0, total: 10 };
  loadingResults = false;

  metrics: MetricRow[] = [];
  shares: ShareRow[] = [];
  expanded = new Set<string>();

  question = '';
  selectedCase = '';
  injectFailure = false;
  asking = false;
  askError: string | null = null;
  asked: AskResult | null = null;

  private pollTimer: ReturnType<typeof setInterval> | null = null;

  constructor(private svc: MultiAgentService) {}

  ngOnInit(): void {
    this.svc.getCases().subscribe({ next: (c) => (this.cases = c), error: () => {} });
    this.fetchStatus();
    this.fetchResults();
  }

  ngOnDestroy(): void {
    this.stopPolling();
  }

  get progressPct(): number {
    return this.status.total ? Math.round((this.status.done / this.status.total) * 100) : 0;
  }

  pickCase(): void {
    const c = this.cases.find((x) => x.case_id === this.selectedCase);
    if (c) this.question = c.question;
  }

  ask(): void {
    if (this.question.trim().length < 3 || this.asking) return;
    this.asking = true;
    this.askError = null;
    this.asked = null;
    this.svc.ask(this.question.trim(), this.injectFailure).subscribe({
      next: (r) => {
        this.asked = r;
        this.asking = false;
      },
      error: (e) => {
        this.askError = e?.error?.detail || 'Request failed';
        this.asking = false;
      },
    });
  }

  startRace(): void {
    this.svc.startRace().subscribe({
      next: () => {
        this.status = { ...this.status, status: 'running', done: 0, error: null };
        this.startPolling();
      },
    });
  }

  toggle(caseId: string): void {
    if (this.expanded.has(caseId)) this.expanded.delete(caseId);
    else this.expanded.add(caseId);
  }

  singleRow(caseId: string) {
    return this.results?.single.rows.find((r) => r.case_id === caseId);
  }

  multiRow(caseId: string) {
    return this.results?.multi.rows.find((r) => r.case_id === caseId);
  }

  caseMode(caseId: string): string {
    return this.cases.find((c) => c.case_id === caseId)?.mode ?? '';
  }

  caseQuestion(caseId: string): string {
    return this.cases.find((c) => c.case_id === caseId)?.question ?? '';
  }

  maxHandoff(handoffs: Handoff[]): number {
    return Math.max(1, ...handoffs.map((h) => h.total_tokens));
  }

  assertionList(a: Record<string, boolean>): { name: string; ok: boolean }[] {
    return Object.entries(a).map(([name, ok]) => ({ name, ok }));
  }

  private fetchStatus(): void {
    this.svc.getStatus().subscribe({
      next: (s) => {
        this.status = s;
        if (s.status === 'running') this.startPolling();
      },
      error: () => {},
    });
  }

  private fetchResults(): void {
    this.loadingResults = true;
    this.svc.getResults().subscribe({
      next: (r) => {
        this.loadingResults = false;
        this.apply(r);
      },
      error: () => (this.loadingResults = false),
    });
  }

  private startPolling(): void {
    if (this.pollTimer) return;
    this.pollTimer = setInterval(() => {
      this.svc.getStatus().subscribe({
        next: (s) => {
          this.status = s;
          if (s.status === 'done' || s.status === 'error') {
            this.stopPolling();
            if (s.status === 'done') this.fetchResults();
          }
        },
        error: () => {},
      });
    }, 4000);
  }

  private stopPolling(): void {
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = null;
  }

  private apply(r: MaResults): void {
    this.results = r;
    const s = r.single;
    const m = r.multi;
    this.metrics = [
      {
        label: 'Pass rate',
        single: `${s.passes}/10 (${Math.round(s.pass_rate * 100)}%)`,
        multi: `${m.passes}/10 (${Math.round(m.pass_rate * 100)}%)`,
        singleWins: s.pass_rate > m.pass_rate,
        multiWins: m.pass_rate > s.pass_rate,
      },
      {
        label: 'p50 latency',
        single: s.p50_latency_s.toFixed(2) + 's',
        multi: m.p50_latency_s.toFixed(2) + 's',
        singleWins: s.p50_latency_s < m.p50_latency_s,
        multiWins: m.p50_latency_s < s.p50_latency_s,
      },
      {
        label: 'p99 latency',
        single: s.p99_latency_s.toFixed(2) + 's',
        multi: m.p99_latency_s.toFixed(2) + 's',
        singleWins: s.p99_latency_s < m.p99_latency_s,
        multiWins: m.p99_latency_s < s.p99_latency_s,
      },
      {
        label: 'Total tokens',
        single: s.total_tokens.toLocaleString(),
        multi: m.total_tokens.toLocaleString(),
        singleWins: s.total_tokens < m.total_tokens,
        multiWins: m.total_tokens < s.total_tokens,
      },
      {
        label: 'Cost / ticket',
        single: '$' + s.cost_per_ticket.toFixed(6),
        multi: '$' + m.cost_per_ticket.toFixed(6),
        singleWins: s.cost_per_ticket < m.cost_per_ticket,
        multiWins: m.cost_per_ticket < s.cost_per_ticket,
      },
    ];

    const totals = new Map<string, number>();
    for (const row of m.rows) {
      for (const h of row.handoffs ?? []) {
        totals.set(h.handoff, (totals.get(h.handoff) ?? 0) + h.total_tokens);
      }
    }
    const grand = Array.from(totals.values()).reduce((a, b) => a + b, 0) || 1;
    this.shares = Array.from(totals.entries())
      .map(([name, tokens]) => ({ name, tokens, share: tokens / grand }))
      .sort((a, b) => b.tokens - a.tokens);
  }
}
