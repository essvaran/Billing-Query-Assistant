import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface TicketInfo {
  ticket_id: string;
  text: string;
  customer_id: string;
  order_id: string;
  expected: string;
  branching: boolean;
}

export interface TicketResult {
  ticket_id: string;
  reply: string;
  total_tokens: number;
  cost_usd: number;
  latency_s: number;
  passed: boolean;
  order_missing?: boolean;
  laps?: number;
  budget_hit?: string | null;
  trace_id?: string | null;
  trace_url?: string | null;
  branching: boolean;
  error?: string | null;
}

export interface SystemAgg {
  pass_rate: number;
  p50_latency_s: number;
  total_tokens: number;
  cost_per_ticket: number;
  tickets: TicketResult[];
}

export interface RaceResults {
  run_at: string;
  model: string;
  agent: SystemAgg;
  workflow: SystemAgg;
  budget_demo_log: string;
  verdict: string;
  tickets: TicketInfo[];
}

export interface RaceStatus {
  status: 'idle' | 'running' | 'done' | 'error';
  started_at: string | null;
  error: string | null;
}

@Injectable({ providedIn: 'root' })
export class RaceService {
  private http = inject(HttpClient);

  getResults(): Observable<RaceResults> {
    return this.http.get<RaceResults>('/api/race/results');
  }

  getStatus(): Observable<RaceStatus> {
    return this.http.get<RaceStatus>('/api/race/status');
  }

  startRace(): Observable<{ status: string }> {
    return this.http.post<{ status: string }>('/api/race/run', {});
  }

  getTickets(): Observable<TicketInfo[]> {
    return this.http.get<TicketInfo[]>('/api/race/tickets');
  }
}
