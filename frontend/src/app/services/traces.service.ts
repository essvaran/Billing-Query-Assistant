import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface TraceChunk {
  chunk_id: string;
  document_id: string | null;
  score: number;
  rank: number;
}

export interface TracePrompt {
  trace_id: string;
  query_type: string;
  system_prompt: string;
  user_prompt: string;
}

export interface TraceRecord {
  trace_id: string;
  timestamp: string;
  question: string;
  query_type: string | null;
  original_query: string;
  rewritten_query: string | null;
  prompt_version: string;
  model: string;
  temperature: number;
  retriever: string;
  top_k: number;
  collection: string;
  retrieved_chunks: TraceChunk[];
  raw_output: string;
  final_answer: string;
  citations: string[];
  citations_valid: boolean;
  retrieval_ms: number;
  generation_ms: number;
  total_ms: number;
  input_tokens: number;
  output_tokens: number;
  error: string | null;
}

export interface TracesResponse {
  traces: TraceRecord[];
  total: number;
  offset: number;
  limit: number;
}

export interface TraceFilters {
  citations_valid?: boolean | null;
  retriever?: string | null;
  error_only?: boolean;
  question?: string;
  limit?: number;
  offset?: number;
}

@Injectable({ providedIn: 'root' })
export class TracesService {
  private http = inject(HttpClient);

  getPrompt(traceId: string): Observable<TracePrompt> {
    return this.http.get<TracePrompt>(`/api/traces/${traceId}/prompt`);
  }

  getTraces(filters: TraceFilters = {}): Observable<TracesResponse> {
    let params = new HttpParams();
    if (filters.citations_valid != null) {
      params = params.set('citations_valid', String(filters.citations_valid));
    }
    if (filters.retriever) {
      params = params.set('retriever', filters.retriever);
    }
    if (filters.error_only) {
      params = params.set('error_only', 'true');
    }
    if (filters.question) {
      params = params.set('question', filters.question);
    }
    params = params.set('limit', String(filters.limit ?? 50));
    params = params.set('offset', String(filters.offset ?? 0));

    return this.http.get<TracesResponse>('/api/traces', { params });
  }
}
