import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { RaceService, RaceResults, TicketInfo, TicketResult, RaceStatus } from '../../services/race.service';

interface MetricRow {
  label: string;
  agentValue: string;
  workflowValue: string;
  agentWins: boolean;
  workflowWins: boolean;
}

@Component({
  selector: 'app-race',
  standalone: true,
  imports: [CommonModule, DatePipe],
  templateUrl: './race.component.html',
  styleUrl: './race.component.scss',
})
export class RaceComponent implements OnInit, OnDestroy {
  results: RaceResults | null = null;
  raceStatus: 'idle' | 'running' | 'done' | 'error' = 'idle';
  statusError: string | null = null;
  loadingResults = false;
  expandedTickets = new Set<string>();
  agentByTicket: Record<string, TicketResult> = {};
  workflowByTicket: Record<string, TicketResult> = {};
  metrics: MetricRow[] = [];

  langfuseUrl = (window as any).__langfuseHost ||
    'https://cloud.langfuse.com';

  private _pollTimer: any = null;

  constructor(private svc: RaceService) {}

  ngOnInit(): void {
    this._fetchStatus();
    this._fetchResults();
  }

  ngOnDestroy(): void {
    if (this._pollTimer) clearInterval(this._pollTimer);
  }

  private _fetchStatus(): void {
    this.svc.getStatus().subscribe({
      next: (s: RaceStatus) => {
        this.raceStatus = s.status;
        this.statusError = s.error;
        if (s.status === 'running') this._startPolling();
      },
      error: () => {},
    });
  }

  private _fetchResults(): void {
    this.loadingResults = true;
    this.svc.getResults().subscribe({
      next: (r) => {
        this.loadingResults = false;
        this._applyResults(r);
        if (this.raceStatus === 'idle') this.raceStatus = 'done';
      },
      error: () => {
        this.loadingResults = false;
      },
    });
  }

  startRace(): void {
    this.svc.startRace().subscribe({
      next: () => {
        this.raceStatus = 'running';
        this._startPolling();
      },
    });
  }

  private _startPolling(): void {
    if (this._pollTimer) return;
    this._pollTimer = setInterval(() => {
      this.svc.getStatus().subscribe({
        next: (s: RaceStatus) => {
          this.raceStatus = s.status;
          this.statusError = s.error;
          if (s.status === 'done' || s.status === 'error') {
            clearInterval(this._pollTimer);
            this._pollTimer = null;
            if (s.status === 'done') this._fetchResults();
          }
        },
        error: () => {},
      });
    }, 5000);
  }

  private _applyResults(r: RaceResults): void {
    this.results = r;
    this.agentByTicket = {};
    this.workflowByTicket = {};
    for (const t of r.agent.tickets) this.agentByTicket[t.ticket_id] = t;
    for (const t of r.workflow.tickets) this.workflowByTicket[t.ticket_id] = t;
    this._buildMetrics(r);
  }

  private _buildMetrics(r: RaceResults): void {
    const a = r.agent;
    const w = r.workflow;
    // Lower latency / tokens / cost wins; higher pass rate wins
    this.metrics = [
      {
        label: 'Pass Rate',
        agentValue: (a.pass_rate * 100).toFixed(0) + '%',
        workflowValue: (w.pass_rate * 100).toFixed(0) + '%',
        agentWins: a.pass_rate > w.pass_rate,
        workflowWins: w.pass_rate > a.pass_rate,
      },
      {
        label: 'p50 Latency',
        agentValue: a.p50_latency_s.toFixed(2) + 's',
        workflowValue: w.p50_latency_s.toFixed(2) + 's',
        agentWins: a.p50_latency_s < w.p50_latency_s,
        workflowWins: w.p50_latency_s < a.p50_latency_s,
      },
      {
        label: 'Total Tokens',
        agentValue: a.total_tokens.toLocaleString(),
        workflowValue: w.total_tokens.toLocaleString(),
        agentWins: a.total_tokens < w.total_tokens,
        workflowWins: w.total_tokens < a.total_tokens,
      },
      {
        label: 'Cost / Ticket',
        agentValue: '$' + a.cost_per_ticket.toFixed(5),
        workflowValue: '$' + w.cost_per_ticket.toFixed(5),
        agentWins: a.cost_per_ticket < w.cost_per_ticket,
        workflowWins: w.cost_per_ticket < a.cost_per_ticket,
      },
    ];
  }

  toggleExpand(ticketId: string): void {
    if (this.expandedTickets.has(ticketId)) {
      this.expandedTickets.delete(ticketId);
    } else {
      this.expandedTickets.add(ticketId);
    }
  }

  isExpanded(ticketId: string): boolean {
    return this.expandedTickets.has(ticketId);
  }

  badgeClass(expected: string): string {
    const map: Record<string, string> = {
      approve: 'badge-approve',
      deny: 'badge-deny',
      escalate: 'badge-escalate',
    };
    return map[expected] ?? 'badge-default';
  }
}
