import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export type TicketStatus = 'new' | 'draft_ready' | 'escalated_by_ai' | 'approved' | 'escalated' | 'rejected';
export type PolicyVersion = 'refund-14d' | 'refund-30d' | 'none';

export interface QueueItem {
  ticket_id: string;
  subject: string;
  preview: string;
  customer: string;
  customer_email: string;
  region: string;
  plan: string;
  policy_version: PolicyVersion;
  order_age_days: number;
  status: TicketStatus;
  ai_reason: string | null;
}

export interface QueueResponse {
  total: number;
  page: number;
  page_size: number;
  items: QueueItem[];
  counts: Partial<Record<TicketStatus, number>>;
}

export interface Citation {
  chunk_id: string;
  slug: string;
  policy_version: PolicyVersion;
  doc_type: string | null;
  display: string;
}

export interface Source {
  chunk_id: string;
  slug: string;
  policy_version: PolicyVersion;
  doc_type: string | null;
  last_updated: string | null;
  text: string;
}

export interface Entitlement {
  customer_id: string;
  plan: string;
  region: string;
  policy_version: PolicyVersion;
  refund_days: number;
  shipping_sla: { standard_days: number; express_days: number };
  refund_check?: { order_id?: string; days_since_purchase?: number; refund_days?: number; eligible?: boolean; error?: string };
}

export interface Violation { code: string; detail: string }

export interface TicketAnswer {
  decision: 'ANSWER' | 'ESCALATE';
  reply: string;
  customer_reply: string;
  reason: string;
  draft: string;
  trace_id: string;
  citations: Citation[];
  entitlement: Entitlement | null;
  sources: Source[];
  tools_called: string[];
  violations: Violation[];
  handoff_id: string;
  laps: number;
  total_tokens: number;
  cost_usd: number;
  latency_ms: number;
  budget_hit: string;
  error: string;
}

export interface Decision { action: string; created_at: string; user_email: string; edit_ratio: number | null }

export interface TicketDetail {
  ticket_id: string;
  subject: string;
  body: string;
  customer: { customer_id: string; name: string; email: string; region: string; plan: string };
  order: { order_id: string; purchase_date: string; amount: number; currency: string; status: string; age_days: number };
  ai: (TicketAnswer & { created_at: string }) | null;
  decisions: Decision[];
}

export interface Step {
  type: 'thinking' | 'llm_response' | 'tool_call' | 'tool_result' | 'guard' | 'done' | 'budget_hit';
  lap?: number;
  tool?: string;
  args?: Record<string, unknown>;
  result?: Record<string, unknown>;
  stage?: 'pre' | 'post';
  blocked?: boolean;
  category?: string | null;
  violations?: string[];
  citations?: number;
  failed?: boolean;      // customer view of a tool_result: the result itself is admin-only
  lap_tokens?: number;
  budget?: string;
}

export interface Job {
  job_id: string;
  status: 'running' | 'done' | 'error';
  trace_id: string;
  steps: Step[];
  result: TicketAnswer | null;
  error: string | null;
}

export interface CustomerOption {
  customer_id: string;
  name: string;
  region: string;
  plan: string;
  policy_version: PolicyVersion;
  orders: { order_id: string; purchase_date: string; age_days: number }[];
}

export interface Escalation {
  handoff_id: string;
  created_at: string;
  ticket_ref: string;
  reason: string;
  summary: string;
  trace_id: string | null;
  status: 'queued' | 'claimed' | 'resolved';
  claimed_by: string | null;
}

export interface FeedbackItem {
  id: number;
  ticket_id: string | null;
  trace_id: string;
  created_at: string;
  reason: string;
  comment: string | null;
  user_email: string;
  status: 'open' | 'case_created';
  eval_case_id: string | null;
}

export interface Article {
  slug: string;
  title: string;
  doc_type: string | null;
  policy_version: PolicyVersion | null;
  applies_to: string | null;
  last_updated: string;
  synthetic: boolean;
  retired: boolean;
  body: string;
}

export interface Span {
  span_id: string;
  parent_id: string | null;
  name: string;
  kind: string;
  started_at: string;
  duration_ms: number;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  status: string;
  attrs: Record<string, unknown>;
}

export interface TraceSummary {
  trace_id: string;
  spans: number;
  total_ms: number;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  llm_calls: number;
  llm_ms: number;
  queue_wait_s: number;
  tool_calls: number;
  mcp_servers_seen: string[];
  errors: string[];
}

export interface FailureMode { mode: string; count: number; severity: string; trace_id: string }

export interface Metrics {
  tickets_processed: number;
  ai_answer_rate: number | null;
  ai_escalation_rate: number | null;
  human_decisions: number;
  edit_rate: number | null;
  cost_per_answered_usd: number | null;
  latency_p50_s: number | null;
  latency_p95_s: number | null;
  second_contact: { deflection_rate: number | null; simulated_reopen_rate: number | null; n: number } | null;
  eval: {
    n: number;
    pass_rate: number;
    tag: string;
    superseded_final_rate: number | null;
    superseded_before: number | null;
    judge_agreement: number | null;
    judge_labels: number;
    cost_per_deflected_usd: number | null;
    failure_modes: FailureMode[];
    both_versions: { n: number; passed: number; pairs: number; pairs_both_correct: number };
  } | null;
  per_day: { day: string; n: number; answered: number; escalated: number }[];
  agreement_target: number;
  min_labels: number;
}

export interface EvalRun {
  run_id: string;
  status: 'running' | 'done' | 'failed';
  log_tail: string[];
  summary: { n: number; passed: number; pass_rate: number; failure_modes: string[] } | null;
  cases: EvalCaseResult[] | null;
}

export interface EvalCaseResult {
  case_id: string;
  passed: boolean;
  decision: string;
  trace_id: string;
  checks: Record<string, boolean>;
  failed_checks: { name: string; detail: string }[];
}

export type Label = 'GOOD' | 'NOT_GOOD';

export interface LabelItem {
  case_id: string;
  subject: string;
  body: string;
  reply: string;
  account_facts: { entitlement: Entitlement | null; order: Record<string, unknown> | null };
  sources: { chunk_id: string; slug: string; policy_version: PolicyVersion; text: string }[];
  label: Label | null;
}

export interface LabelQueue {
  tag: string;
  labeler: string;
  queue_experience: string;
  min_labels: number;
  target: number;
  items: LabelItem[];
}

export interface JudgeAgreement {
  version: string;
  model: string | null;
  n: number;
  agree?: number;
  agreement?: number;
  judge_good_human_not_good?: number;
  judge_not_good_human_good?: number;
  meets_target?: boolean;
  status: string;
}

export interface AgreementResponse {
  tag: string;
  labelled: number;
  answers: number;
  min_labels: number;
  status: 'locked' | 'measured';
  judges?: Record<string, JudgeAgreement>;
}

export interface QueueQuery { status?: string; q?: string; policy?: string; region?: string; page?: number }

@Injectable({ providedIn: 'root' })
export class Tier1Service {
  private http = inject(HttpClient);
  private base = '/api/tier1';

  tickets(query: QueueQuery): Observable<QueueResponse> {
    let params = new HttpParams();
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null && v !== '') params = params.set(k, String(v));
    }
    return this.http.get<QueueResponse>(`${this.base}/tickets`, { params });
  }
  ticket(id: string): Observable<TicketDetail> { return this.http.get<TicketDetail>(`${this.base}/tickets/${id}`); }
  randomTicket(seed?: number): Observable<{ seed: number; ticket_id: string }> {
    const params = seed === undefined ? new HttpParams() : new HttpParams().set('seed', seed);
    return this.http.get<{ seed: number; ticket_id: string }>(`${this.base}/random-ticket`, { params });
  }
  meCustomer(): Observable<{ customer: { customer_id: string; region: string; plan: string; policy_version: PolicyVersion } | null; can_choose: boolean }> {
    return this.http.get<{ customer: { customer_id: string; region: string; plan: string; policy_version: PolicyVersion } | null; can_choose: boolean }>(`${this.base}/me/customer`);
  }
  customers(): Observable<CustomerOption[]> { return this.http.get<CustomerOption[]>(`${this.base}/customers`); }

  answer(body: { ticket_id?: string; text?: string; subject?: string; customer_id?: string; order_id?: string }):
    Observable<{ job_id: string; trace_id: string }> {
    return this.http.post<{ job_id: string; trace_id: string }>(`${this.base}/answer`, body);
  }
  job(id: string): Observable<Job> { return this.http.get<Job>(`${this.base}/jobs/${id}`); }

  /** Polls a job with a gentle backoff; unsubscribing cancels the polling. */
  pollJob(id: string): Observable<Job> {
    return new Observable<Job>(subscriber => {
      let delay = 700;
      let stopped = false;
      let timer: ReturnType<typeof setTimeout> | undefined;
      const tick = () => {
        if (stopped) return;
        this.job(id).subscribe({
          next: job => {
            subscriber.next(job);
            if (job.status === 'running') {
              delay = Math.min(delay * 1.25, 2500);
              timer = setTimeout(tick, delay);
            } else {
              subscriber.complete();
            }
          },
          error: err => subscriber.error(err),
        });
      };
      tick();
      return () => { stopped = true; if (timer) clearTimeout(timer); };
    });
  }

  decide(id: string, action: 'approve' | 'edit' | 'escalate' | 'reject', text?: string) {
    return this.http.post<{ action: string; edit_ratio: number | null }>(`${this.base}/tickets/${id}/decision`, { action, text });
  }
  sendFeedback(body: { trace_id: string; ticket_id?: string; reason: string; comment?: string }) {
    return this.http.post<{ id: number }>(`${this.base}/feedback`, body);
  }
  feedbackInbox(): Observable<FeedbackItem[]> { return this.http.get<FeedbackItem[]>(`${this.base}/feedback`); }
  feedbackToCase(id: number) {
    return this.http.post<{ case_id: string; expected_decision: string }>(`${this.base}/feedback/${id}/eval-case`, {});
  }
  escalations(status = ''): Observable<Escalation[]> {
    const params = status ? new HttpParams().set('status', status) : new HttpParams();
    return this.http.get<Escalation[]>(`${this.base}/escalations`, { params });
  }
  escalationStatus(id: string, status: 'claimed' | 'resolved') {
    return this.http.post(`${this.base}/escalations/${id}/status`, { status });
  }
  article(slug: string): Observable<Article> { return this.http.get<Article>(`${this.base}/articles/${slug}`); }
  labelRuns(): Observable<{ tag: string; answers: number }[]> {
    return this.http.get<{ tag: string; answers: number }[]>(`${this.base}/labels/runs`);
  }
  labelQueue(tag: string): Observable<LabelQueue> {
    return this.http.get<LabelQueue>(`${this.base}/labels/queue`, { params: new HttpParams().set('tag', tag) });
  }
  setLabel(tag: string, caseId: string, label: Label | null) {
    return this.http.post<{ case_id: string; label: Label | null }>(`${this.base}/labels/${caseId}`, { tag, label });
  }
  setLabeler(name: string, queueExperience: string) {
    return this.http.put<{ labeler: string; queue_experience: string }>(`${this.base}/labels/labeler`, { name, queue_experience: queueExperience });
  }
  labelAgreement(tag: string): Observable<AgreementResponse> {
    return this.http.get<AgreementResponse>(`${this.base}/labels/agreement`, { params: new HttpParams().set('tag', tag) });
  }
  claimTopics(): Observable<{ claim_topics: string }> { return this.http.get<{ claim_topics: string }>(`${this.base}/rules`); }
  metrics(): Observable<Metrics> { return this.http.get<Metrics>(`${this.base}/metrics`); }
  trace(id: string): Observable<{ summary: TraceSummary; spans: Span[] }> {
    return this.http.get<{ summary: TraceSummary; spans: Span[] }>(`${this.base}/traces/${id}`);
  }
  evalRun(only: string | null): Observable<{ run_id: string }> {
    return this.http.post<{ run_id: string }>(`${this.base}/eval/run`, { only, tag: only ? 'ui_' + only : 'ui' });
  }
  /** Run one regression case (created from a reported failure) and see each check red or green. */
  runRegressionCase(caseId: string): Observable<{ run_id: string }> {
    return this.http.post<{ run_id: string }>(`${this.base}/eval/run`,
      { cases: 'regression', case_id: caseId, tag: 'reg_' + caseId.toLowerCase() });
  }
  evalStatus(runId: string): Observable<EvalRun> { return this.http.get<EvalRun>(`${this.base}/eval/runs/${runId}`); }
}
