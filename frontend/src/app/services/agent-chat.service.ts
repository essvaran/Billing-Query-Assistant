import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface AgentStep {
  type: 'thinking' | 'llm_response' | 'tool_call' | 'tool_result' | 'done' | 'budget_hit' | 'error';
  lap?: number;
  // thinking
  // llm_response
  finish_reason?: string;
  lap_tokens?: number;
  cumulative_tokens?: number;
  // tool_call / tool_result
  tool?: string;
  args?: Record<string, unknown>;
  result?: Record<string, unknown>;
  // done
  reply?: string;
  laps?: number;
  total_tokens?: number;
  cost_usd?: number;
  latency_s?: number;
  passed?: boolean;
  // budget_hit
  budget?: string;
  value?: number | string;
  limit?: number | string;
  log?: string;
  // error
  error?: string;
}

export interface AgentResult {
  ticket_id: string;
  reply: string;
  laps: number;
  total_tokens: number;
  cost_usd: number;
  latency_s: number;
  passed: boolean;
  budget_hit: string | null;
  error: string | null;
  trace_id: string | null;
  trace_url: string | null;
}

export interface JobStatus {
  status: 'running' | 'done' | 'error';
  steps: AgentStep[];
  result: AgentResult | null;
  error: string | null;
}

export interface TicketInfo {
  ticket_id: string;
  text: string;
  customer_id: string;
  order_id: string;
  expected: string;
  branching: boolean;
}

@Injectable({ providedIn: 'root' })
export class AgentChatService {
  private http = inject(HttpClient);

  getTickets(): Observable<TicketInfo[]> {
    return this.http.get<TicketInfo[]>('/api/agent/tickets');
  }

  startRun(ticketId: string, tightBudget = false): Observable<{ job_id: string }> {
    return this.http.post<{ job_id: string }>('/api/agent/run', {
      ticket_id: ticketId,
      tight_budget: tightBudget,
    });
  }

  startRunRaw(body: Record<string, unknown>): Observable<{ job_id: string }> {
    return this.http.post<{ job_id: string }>('/api/agent/run', body);
  }

  getStatus(jobId: string): Observable<JobStatus> {
    return this.http.get<JobStatus>(`/api/agent/status/${jobId}`);
  }
}
