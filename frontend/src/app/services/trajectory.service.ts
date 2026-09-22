import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface ToolStep {
  tool: string;
  args: Record<string, unknown>;
  result: Record<string, unknown>;
  valid_args: boolean;
}

export interface FailureModeEntry {
  mode: string;
  ticket_id: string;
  detail: string;
}

export interface TrajectoryResult {
  ticket_id: string;
  expected_verdict: string;
  outcome_passed: boolean;
  reply: string;
  tool_steps: ToolStep[];
  expected_sequences: string[][];
  sequence_matched: boolean;
  tool_choice_correct: boolean;
  all_args_valid: boolean;
  step_count: number;
  optimal_step_count: number;
  step_efficiency: number;
  cost_usd: number;
  latency_s: number;
  total_tokens: number;
  laps: number;
  failure_modes: FailureModeEntry[];
  trajectory_passed: boolean;
  trace_url: string | null;
}

export interface GapExample {
  ticket_id: string;
  expected_verdict: string;
  reply_snippet: string;
  actual_sequence: string[];
  expected_sequences: string[][];
  failure_modes: string[];
  explanation: string;
}

export interface TrajectoryEvalReport {
  run_id: string;
  run_at: string;
  results: TrajectoryResult[];
  tool_choice_accuracy: number;
  argument_validity_rate: number;
  step_efficiency_mean: number;
  cost_p50: number;
  cost_max: number;
  outcome_pass_count: number;
  trajectory_pass_count: number;
  gap: number;
  gap_example: GapExample | null;
  failure_mode_counts: Record<string, number>;
  all_failure_modes: FailureModeEntry[];
}

export interface ExpectedSequenceEntry {
  ticket_id: string;
  text: string;
  expected_verdict: string;
  branching: boolean;
  adversarial: boolean;
  sequences: string[][];
  expected_args: Record<string, Record<string, string>>;
}

export interface RegressionRow {
  mode: string;
  before: number;
  after: number;
  delta: number;
  status: string;
}

export interface MitigationReport {
  mitigation_name: string;
  description: string;
  before: TrajectoryEvalReport;
  after: TrajectoryEvalReport;
  deltas: {
    tool_choice_accuracy: number;
    argument_validity_rate: number;
    step_efficiency_mean: number;
    cost_p50: number;
    cost_max: number;
  };
  top_failure_mode: {
    mode: string;
    before_count: number;
    after_count: number;
  };
  price_paid: {
    latency_delta_mean_s: number;
    tokens_delta_mean: number;
    cost_delta_mean_usd: number;
  };
  regression_table: RegressionRow[];
  regression_detected: boolean;
  regression_details: string;
}

export interface InjectionResult {
  payload_id: string;
  payload_name: string;
  payload_text: string;
  target_ticket: string;
  expected_verdict: string;
  undefended: {
    reply: string;
    agent_verdict: string;
    injection_succeeded: boolean;
  };
  defended: {
    reply: string;
    agent_verdict: string;
    injection_succeeded: boolean;
    defense_held: boolean;
  };
  what_still_gets_through: string;
}

export interface EvalStatus {
  status: 'idle' | 'running' | 'done' | 'error';
  started_at: string | null;
  error: string | null;
  progress?: Record<string, unknown>;
}

@Injectable({ providedIn: 'root' })
export class TrajectoryService {
  private http = inject(HttpClient);

  getExpectedSequences(): Observable<ExpectedSequenceEntry[]> {
    return this.http.get<ExpectedSequenceEntry[]>('/api/trajectory/expected-sequences');
  }

  startEval(): Observable<{ status: string }> {
    return this.http.post<{ status: string }>('/api/trajectory/run', {});
  }

  getStatus(): Observable<EvalStatus> {
    return this.http.get<EvalStatus>('/api/trajectory/status');
  }

  getResults(): Observable<TrajectoryEvalReport> {
    return this.http.get<TrajectoryEvalReport>('/api/trajectory/results');
  }

  startMitigation(): Observable<{ status: string }> {
    return this.http.post<{ status: string }>('/api/trajectory/mitigate', {});
  }

  getMitigationStatus(): Observable<EvalStatus> {
    return this.http.get<EvalStatus>('/api/trajectory/mitigation-status');
  }

  getMitigationResults(): Observable<MitigationReport> {
    return this.http.get<MitigationReport>('/api/trajectory/mitigation-results');
  }

  startInjectionTest(): Observable<{ status: string }> {
    return this.http.post<{ status: string }>('/api/trajectory/injection/run', {});
  }

  getInjectionStatus(): Observable<EvalStatus> {
    return this.http.get<EvalStatus>('/api/trajectory/injection/status');
  }

  getInjectionResults(): Observable<InjectionResult[]> {
    return this.http.get<InjectionResult[]>('/api/trajectory/injection/results');
  }
}
