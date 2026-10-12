import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface MaCase {
  case_id: string;
  question: string;
  mode: string;
  expected_behavior: string;
}

export interface Handoff {
  handoff: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  ms: number;
  note: string;
}

export interface ArmRow {
  case_id: string;
  answer: string;
  latency_s: number;
  tokens: number;
  assertions_ok: boolean;
  judge: string;
  passed: boolean;
  error: string | null;
  handoffs?: Handoff[];
}

export interface ArmAgg {
  pass_rate: number;
  passes: number;
  p50_latency_s: number;
  p99_latency_s: number;
  total_tokens: number;
  cost_per_ticket: number;
  rows: ArmRow[];
}

export interface AgentCard {
  name: string;
  description: string;
  version: string;
  defaultInputModes: string[];
  defaultOutputModes: string[];
  authentication: { schemes: string[] };
  skills: { id: string; name: string; description: string; inputModes: string[]; outputModes: string[] }[];
}

export interface MaResults {
  run_at: string;
  cases: string[];
  single: ArmAgg;
  multi: ArmAgg;
  multiplier: number;
  failure_behaviour: string;
  verdict_keep: boolean;
  files: Record<string, string | null>;
  agent_card: AgentCard | null;
}

export interface MaStatus {
  status: 'idle' | 'running' | 'done' | 'error';
  started_at: string | null;
  error: string | null;
  done: number;
  total: number;
}

export interface AskResult {
  question: string;
  inject_failure: boolean;
  single: {
    answer: string;
    tokens: number;
    cost_usd: number;
    latency_s: number;
    chunk_ids: string[];
    assertions: Record<string, boolean>;
  };
  multi: {
    answer: string;
    tokens: number;
    cost_usd: number;
    latency_s: number;
    chunk_ids: string[];
    assertions: Record<string, boolean>;
    triage: { intent?: string; normalized_query?: string; mentioned_codes?: string[] };
    handoffs: Handoff[];
    policy_lookup_failed: boolean;
    tool_attempts: number;
  };
}

@Injectable({ providedIn: 'root' })
export class MultiAgentService {
  private http = inject(HttpClient);

  getCases(): Observable<MaCase[]> {
    return this.http.get<MaCase[]>('/api/multiagent/cases');
  }

  getResults(): Observable<MaResults> {
    return this.http.get<MaResults>('/api/multiagent/results');
  }

  getStatus(): Observable<MaStatus> {
    return this.http.get<MaStatus>('/api/multiagent/status');
  }

  startRace(): Observable<{ status: string }> {
    return this.http.post<{ status: string }>('/api/multiagent/run', {});
  }

  ask(question: string, injectFailure: boolean): Observable<AskResult> {
    return this.http.post<AskResult>('/api/multiagent/ask', {
      question,
      inject_failure: injectFailure,
    });
  }
}
