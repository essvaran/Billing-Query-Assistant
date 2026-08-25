import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface TraceChunk {
  chunk_id: string;
  document_id: string | null;
  score: number;
  rank: number;
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

export interface TracePrompt {
  trace_id: string;
  query_type: string;
  system_prompt: string;
  user_prompt: string;
}

export interface ReplayChunk {
  chunk_id: string;
  article_id: string | null;
  section: string | null;
  text: string;
}

export interface ReplayResult {
  trace_id: string;
  question: string;
  original_model: string;
  replay_model: string;
  model_matched: boolean;
  original_raw_output: string;
  original_citations: string[];
  original_citations_valid: boolean;
  replayed_raw_output: string;
  replayed_citations: string[];
  replayed_citations_valid: boolean;
  chunks_used: ReplayChunk[];
  chunks_available: boolean;
  replayed_input_tokens: number;
  replayed_output_tokens: number;
  outputs_match: boolean;
}

@Injectable({ providedIn: 'root' })
export class SampleService {
  constructor(private http: HttpClient) {}

  getSample(): Observable<TraceRecord[]> {
    return this.http.get<TraceRecord[]>('/api/traces/sample');
  }

  replayTrace(traceId: string): Observable<ReplayResult> {
    return this.http.get<ReplayResult>(`/api/traces/${traceId}/replay`);
  }

  getPrompt(traceId: string): Observable<TracePrompt> {
    return this.http.get<TracePrompt>(`/api/traces/${traceId}/prompt`);
  }
}
