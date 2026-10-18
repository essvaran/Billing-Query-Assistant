import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface ObsMeta {
  prompt_version: string;
  demo_tools_enabled: boolean;
  alerts_enabled: boolean;
  langfuse_configured: boolean;
  drill_bar_seconds: number;
  drill_complaint: string;
  tenx_baseline_rpm: number;
  tenx_multiplier: number;
  langfuse_url: string | null;
  feedback_new_down: number;
}

export interface TraceSummary {
  trace_id: string;
  timestamp: string;
  question: string;
  answer_preview: string;
  prompt_version: string;
  model: string;
  user_email: string | null;
  citations_valid: boolean | null;
  unverified: boolean;
  is_refusal: boolean;
  total_ms: number;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  error: string | null;
}

export interface TraceList {
  source: string;
  scanned: number;
  truncated: boolean;
  total: number;
  limit: number;
  offset: number;
  items: TraceSummary[];
}

export interface TraceFilter {
  after?: string;
  before?: string;
  keyword?: string;
  prompt_version?: string;
  cost_above?: number | null;
  unverified?: boolean;
  errors_only?: boolean;
  user?: string;
  limit?: number;
  offset?: number;
}

export interface Span {
  name: string;
  latency_ms: number | null;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  logged: boolean;
}

export interface TraceChunk {
  chunk_id: string;
  document_id?: string | null;
  score?: number;
  rank?: number;
}

export interface TraceDetail extends TraceSummary {
  final_answer: string;
  raw_output: string | null;
  citations: string[];
  retriever: string;
  collection: string;
  top_k: number;
  temperature: number;
  retrieved_chunks: TraceChunk[];
  retrieved_context_ids: string[];
  context_recorded: boolean;
  eval_case_id: string | null;
  langfuse_url: string | null;
  feedback: FeedbackItem[];
  cost_by_stage: { retrieval_usd: number; generation_usd: number; tools_usd: number };
  spans: Span[];
}

export interface FeedbackItem {
  id: number;
  trace_id: string;
  user_email: string;
  rating: 'up' | 'down';
  reason_code: string | null;
  reason_label: string | null;
  comment: string | null;
  status: 'new' | 'reviewed';
  created_at: string;
  updated_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  admin_note: string | null;
  question?: string | null;
  answer_preview?: string;
  prompt_version?: string | null;
  answered_at?: string | null;
  langfuse_url?: string | null;
}

export interface FeedbackList {
  total: number;
  limit: number;
  offset: number;
  counts: { new_down: number; down: number; up: number };
  items: FeedbackItem[];
}

export interface EvalCase {
  case_id: string;
  question: string;
  mode: string;
  expected_behavior: string;
  is_regression?: boolean;
  regression_trace_id?: string;
  notes?: string;
  last_result?: { passed: boolean; run_id: string; prompt_version: string; at: string } | null;
}

export interface GroupStats {
  prompt_version?: string;
  requests: number;
  llm_requests: number;
  avg_cost_usd: number;
  p50_cost_usd: number;
  p95_cost_usd: number;
  max_cost_usd: number;
  avg_input_tokens: number;
  avg_output_tokens: number;
  avg_retrieval_ms: number;
  avg_generation_ms: number;
  p50_retrieval_ms: number;
  p50_generation_ms: number;
  models: string[];
  unverified_answers: number;
  cost_per_1000_usd: number;
}

export interface Stats {
  window_days: number;
  scanned: number;
  truncated: boolean;
  overall: GroupStats;
  stages: { stage: string; avg_cost_usd: number; avg_latency_ms: number; note: string }[];
  by_prompt_version: GroupStats[];
  traffic: { peak_requests_per_min: number; peak_tokens_per_min: number };
}

export interface Constraint {
  name: string;
  limit: number;
  needed: number;
  ratio: number;
  minutes_to_break: number | null;
}

export interface TenX {
  baseline_rpm: number;
  multiplier: number;
  requests_per_min: number;
  avg_tokens_per_request: number;
  avg_generation_ms: number;
  cost_per_request_usd: number;
  daily_cost_usd: number;
  constraints: Constraint[];
  verdict: string;
  assumptions: string;
}

export interface AlertConfig {
  enabled: boolean;
  smtp_host: string;
  smtp_port: number;
  email_from: string;
  email_to: string;
  password_set: boolean;
  missing: string[];
  cost_threshold_usd: number;
  latency_threshold_ms: number;
  rate_limit_seconds: number;
  conditions: string[];
}

export interface AlertRow {
  id: number;
  ts: string;
  alert_type: string;
  trace_id: string | null;
  reason: string | null;
  status: 'sent' | 'failed' | 'suppressed' | 'test';
  detail: string | null;
}

export interface DrillRow {
  id: number;
  created_at: string;
  trace_id: string;
  seconds: number;
  slice: string;
  notes: string | null;
  user_email: string;
  passed_bar: boolean;
}

export interface EvalRun {
  run_id: string;
  prompt_version: string;
  started_at: string;
  finished_at: string | null;
  total: number;
  passed: number;
  status: 'running' | 'done' | 'error';
  source: string;
  user_email: string | null;
  error: string | null;
}

export interface AssertionDetail {
  name: string;
  passed: boolean;
  detail: string;
}

export interface EvalResult {
  case_id: string;
  passed: boolean;
  detail: AssertionDetail[];
  answer: string | null;
  trace_id: string | null;
}

export interface EvalRunDetail {
  run: EvalRun;
  results: EvalResult[];
}

export interface DiffRow {
  case_id: string;
  base: boolean | null;
  head: boolean | null;
  change: 'fixed' | 'regressed' | 'same_fail' | 'same_pass' | 'new' | 'missing';
}

export interface EvalDiff {
  base: string;
  head: string;
  summary: Record<string, number>;
  rows: DiffRow[];
}

export function apiError(err: unknown): string {
  const e = err as { status?: number; error?: { detail?: unknown }; message?: string };
  const detail = e && e.error ? e.error.detail : undefined;
  if (typeof detail === 'string') {
    return detail;
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string };
    return first.msg || 'Invalid request';
  }
  if (e && e.status === 0) {
    return 'Cannot reach the API. Is the backend running?';
  }
  if (e && e.status === 403) {
    return 'Admin access required.';
  }
  return (e && e.message) || 'Request failed.';
}

@Injectable({ providedIn: 'root' })
export class ObservabilityService {
  private http = inject(HttpClient);
  private base = '/api/obs';

  meta(): Observable<ObsMeta> {
    return this.http.get<ObsMeta>(this.base + '/meta');
  }

  traces(filter: TraceFilter): Observable<TraceList> {
    let params = new HttpParams();
    const keys = Object.keys(filter) as (keyof TraceFilter)[];
    for (const key of keys) {
      const value = filter[key];
      if (value === undefined || value === null || value === '' || value === false) {
        continue;
      }
      params = params.set(key, String(value));
    }
    return this.http.get<TraceList>(this.base + '/traces', { params: params });
  }

  trace(id: string): Observable<TraceDetail> {
    return this.http.get<TraceDetail>(this.base + '/traces/' + encodeURIComponent(id));
  }

  createEvalCase(id: string, body: { expected_behavior: string; mode: string; notes: string }): Observable<EvalCase> {
    return this.http.post<EvalCase>(this.base + '/traces/' + encodeURIComponent(id) + '/eval-case', body);
  }

  stats(days: number): Observable<Stats> {
    return this.http.get<Stats>(this.base + '/stats', { params: { days: String(days) } });
  }

  tenx(baselineRpm: number, multiplier: number): Observable<TenX> {
    return this.http.get<TenX>(this.base + '/tenx', {
      params: { baseline_rpm: String(baselineRpm), multiplier: String(multiplier) },
    });
  }

  alertConfig(): Observable<AlertConfig> {
    return this.http.get<AlertConfig>(this.base + '/alerts/config');
  }

  alerts(status?: string): Observable<AlertRow[]> {
    let params = new HttpParams();
    if (status) {
      params = params.set('status', status);
    }
    return this.http.get<AlertRow[]>(this.base + '/alerts', { params: params });
  }

  testAlert(): Observable<{ ok: boolean; message: string }> {
    return this.http.post<{ ok: boolean; message: string }>(this.base + '/alerts/test', {});
  }

  drills(): Observable<DrillRow[]> {
    return this.http.get<DrillRow[]>(this.base + '/drills');
  }

  recordDrill(body: { trace_id: string; seconds: number; slice: string; notes: string }): Observable<{ seconds: number; passed_bar: boolean }> {
    return this.http.post<{ seconds: number; passed_bar: boolean }>(this.base + '/drills', body);
  }

  evalCases(): Observable<EvalCase[]> {
    return this.http.get<EvalCase[]>(this.base + '/eval/cases');
  }

  runCase(caseId: string): Observable<EvalResult & { run_id: string }> {
    return this.http.post<EvalResult & { run_id: string }>(this.base + '/eval/cases/' + encodeURIComponent(caseId) + '/run', {});
  }

  startSuite(): Observable<{ run_id: string }> {
    return this.http.post<{ run_id: string }>(this.base + '/eval/runs', {});
  }

  evalRuns(): Observable<EvalRun[]> {
    return this.http.get<EvalRun[]>(this.base + '/eval/runs');
  }

  evalRun(runId: string): Observable<EvalRunDetail> {
    return this.http.get<EvalRunDetail>(this.base + '/eval/runs/' + encodeURIComponent(runId));
  }

  evalDiff(base: string, head: string): Observable<EvalDiff> {
    return this.http.get<EvalDiff>(this.base + '/eval/diff', { params: { base: base, head: head } });
  }

  feedback(filter: { rating?: string; status?: string; limit: number; offset: number }): Observable<FeedbackList> {
    let params = new HttpParams().set('limit', String(filter.limit)).set('offset', String(filter.offset));
    if (filter.rating) {
      params = params.set('rating', filter.rating);
    }
    if (filter.status) {
      params = params.set('status', filter.status);
    }
    return this.http.get<FeedbackList>(this.base + '/feedback', { params: params });
  }

  reviewFeedback(id: number, status: 'new' | 'reviewed', adminNote: string): Observable<{ id: number; status: string }> {
    return this.http.post<{ id: number; status: string }>(this.base + '/feedback/' + id + '/review', {
      status: status,
      admin_note: adminNote,
    });
  }

  plantDemo(): Observable<{ trace_id: string; timestamp: string }> {
    return this.http.post<{ trace_id: string; timestamp: string }>(this.base + '/demo/plant', {});
  }
}
