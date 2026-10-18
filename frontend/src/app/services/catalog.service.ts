import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { RefCategory, RefValue } from '../shared/ref-data';

/** Admin API for everything that used to be hard-coded: lists, settings, prices, prompts, guard rules, eval data, Tier-1 data. */

export interface SettingRow {
  key: string; group: string; label: string; description: string; type: 'int' | 'float' | 'str' | 'bool' | 'json';
  min: number | null; max: number | null; value: unknown; default: unknown; effective: unknown;
  env: string | null; overridden_by_env: boolean; restart_required: boolean; updated_at: string; updated_by: string;
}
export interface PriceRow { model: string; input_per_1m: number; output_per_1m: number; source: string; checked_on: string; updated_at?: string; updated_by?: string }
export interface GateCheck { check: string; passed: boolean; detail: string }
export interface GateReport { passed: boolean; checks: GateCheck[] }
export interface PromptVersion { id: number; name: string; version: number; body: string; status: 'draft' | 'active' | 'retired' | 'rejected';
  note: string; test_report: GateReport; created_at: string; created_by: string; activated_at: string | null }
export interface PromptRow { name: string; label: string; description: string; used_by: string; placeholders: string[];
  required_phrases: string[]; active_version: number | null; versions: PromptVersion[] }
export interface GuardRules { pre: { category: string; reason: string; detail?: string; patterns: string[] }[]; post: Record<string, string>; violation_reason?: Record<string, string> }
export interface GuardVersion { id: number; version: number; rules: GuardRules; status: string; note: string; test_report: GateReport; created_at: string; created_by: string }
export interface GuardExample { id: number; stage: 'pre' | 'post'; text: string; expect: string; note: string; created_at: string; created_by: string }
export interface ChangeRow { id: number; at: string; actor: string; entity: string; entity_id: string; action: string; before: string | null; after: string | null }
export interface EvalCaseRow { case_id: string; suite: string; active: boolean; source: string; updated_at: string; updated_by: string; [k: string]: unknown }
export interface EvalRunRow { tag: string; suite: string; status: string; notes: string; created_at: string; updated_at: string; n_rows: number; n: number | null; passed: number | null; pass_rate: number | null }

@Injectable({ providedIn: 'root' })
export class CatalogService {
  private http = inject(HttpClient);
  private a = '/api/admin/catalog';

  // reference lists
  createValue(category: string, v: Partial<RefValue>) { return this.http.post<RefValue>(`${this.a}/ref/${category}`, v); }
  updateValue(category: string, code: string, v: Partial<RefValue>) { return this.http.put<RefValue>(`${this.a}/ref/${category}/${encodeURIComponent(code)}`, v); }
  deleteValue(category: string, code: string) { return this.http.delete(`${this.a}/ref/${category}/${encodeURIComponent(code)}`); }

  // settings
  settings(): Observable<SettingRow[]> { return this.http.get<SettingRow[]>(`${this.a}/settings`); }
  setSetting(key: string, value: unknown) { return this.http.put<SettingRow>(`${this.a}/settings/${key}`, { value }); }
  resetSetting(key: string) { return this.http.post<SettingRow>(`${this.a}/settings/${key}/reset`, {}); }

  // prices
  prices(): Observable<PriceRow[]> { return this.http.get<PriceRow[]>(`${this.a}/prices`); }
  createPrice(p: PriceRow) { return this.http.post<PriceRow>(`${this.a}/prices`, p); }
  updatePrice(p: PriceRow) { return this.http.put<PriceRow>(`${this.a}/prices/${p.model}`, p); }
  deletePrice(model: string) { return this.http.delete(`${this.a}/prices/${model}`); }

  // prompts
  prompts(): Observable<PromptRow[]> { return this.http.get<PromptRow[]>(`${this.a}/prompts`); }
  testPrompt(name: string, body: string) { return this.http.post<GateReport>(`${this.a}/prompts/${name}/test`, { body }); }
  draftPrompt(name: string, body: string, note: string) {
    return this.http.post<{ version: number; status: string; test_report: GateReport }>(`${this.a}/prompts/${name}/versions`, { body, note });
  }
  activatePrompt(name: string, version: number) { return this.http.post(`${this.a}/prompts/${name}/versions/${version}/activate`, {}); }
  deletePromptVersion(name: string, version: number) { return this.http.delete(`${this.a}/prompts/${name}/versions/${version}`); }

  // guard rules
  guards(): Observable<{ versions: GuardVersion[]; examples: GuardExample[]; active_version: number | null }> {
    return this.http.get<{ versions: GuardVersion[]; examples: GuardExample[]; active_version: number | null }>(`${this.a}/guards`);
  }
  testGuards(rules: GuardRules) { return this.http.post<GateReport>(`${this.a}/guards/test`, { rules }); }
  draftGuards(rules: GuardRules, note: string) { return this.http.post<{ version: number; status: string; test_report: GateReport }>(`${this.a}/guards/versions`, { rules, note }); }
  activateGuards(version: number) { return this.http.post(`${this.a}/guards/versions/${version}/activate`, {}); }
  deleteGuards(version: number) { return this.http.delete(`${this.a}/guards/versions/${version}`); }
  saveExample(e: Partial<GuardExample>) {
    const body = { stage: e.stage, text: e.text, expect: e.expect, note: e.note ?? '' };
    return e.id ? this.http.put<{ id: number; live_rules_pass: boolean; test_report: GateReport }>(`${this.a}/guards/examples/${e.id}`, body)
                : this.http.post<{ id: number; live_rules_pass: boolean; test_report: GateReport }>(`${this.a}/guards/examples`, body);
  }
  deleteExample(id: number) { return this.http.delete(`${this.a}/guards/examples/${id}`); }

  // change log
  changes(entity = '', limit = 200): Observable<ChangeRow[]> {
    return this.http.get<ChangeRow[]>(`${this.a}/changes`, { params: new HttpParams().set('entity', entity).set('limit', limit) });
  }

  // eval data
  evalCases(suite = ''): Observable<EvalCaseRow[]> { return this.http.get<EvalCaseRow[]>('/api/admin/eval/cases', { params: new HttpParams().set('suite', suite) }); }
  createCase(caseId: string, suite: string, data: Record<string, unknown>) { return this.http.post<EvalCaseRow>('/api/admin/eval/cases', { case_id: caseId || null, suite, data }); }
  updateCase(caseId: string, suite: string, data: Record<string, unknown>) { return this.http.put<EvalCaseRow>(`/api/admin/eval/cases/${caseId}`, { suite, data }); }
  setCaseActive(caseId: string, active: boolean) { return this.http.post<EvalCaseRow>(`/api/admin/eval/cases/${caseId}/active`, { active }); }
  deleteCase(caseId: string) { return this.http.delete(`/api/admin/eval/cases/${caseId}`); }
  evalRuns(suite = ''): Observable<EvalRunRow[]> { return this.http.get<EvalRunRow[]>('/api/admin/eval/runs', { params: new HttpParams().set('suite', suite) }); }
  saveRunNotes(tag: string, notes: string) { return this.http.put(`/api/admin/eval/runs/${tag}/notes`, { notes }); }
  deleteRun(tag: string) { return this.http.delete(`/api/admin/eval/runs/${tag}`); }
  week6(): Observable<Week6> { return this.http.get<Week6>('/api/admin/eval/week6'); }

  // Tier-1 data
  tier1List(kind: 'customers' | 'orders' | 'tickets', q = ''): Observable<Record<string, unknown>[]> {
    return this.http.get<Record<string, unknown>[]>(`/api/admin/tier1/${kind}`, { params: new HttpParams().set('q', q) });
  }
  tier1Create(kind: string, row: Record<string, unknown>) { return this.http.post(`/api/admin/tier1/${kind}`, row); }
  tier1Update(kind: string, id: string, row: Record<string, unknown>) { return this.http.put(`/api/admin/tier1/${kind}/${id}`, row); }
  tier1Delete(kind: string, id: string) { return this.http.delete(`/api/admin/tier1/${kind}/${id}`); }
}

export interface Week6Row {
  case_id: string; question: string; mode: string; expected_behavior: string; is_regression: boolean;
  regression_trace_id: string | null; reply: string; checks: Record<string, boolean>; passed: boolean;
  judge: { verdict: string; version: string } | null; judge_alt: { verdict: string; version: string } | null; human_label: string | null;
}
export interface Week6Judge {
  version: string | null; good: number; not_good: number; disagreements: string[];
  agreement: { n: number; agree?: number; agreement?: number; status: string };
}
export interface Week6 {
  run: { tag: string; notes: string; created_at: string; updated_at: string; summary: Record<string, unknown> };
  n: number; labelled: number; regressions: string[]; checks: string[];
  by_mode: { mode: string; label: string; short: string; description: string; n: number; checks: Record<string, number>; judge_good: Partial<Record<string, number>> }[];
  judges: Record<string, Week6Judge>; rows: Week6Row[]; prompts: Record<string, string>;
}

export type { RefCategory, RefValue };
