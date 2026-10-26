import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface ChunkResult {
  rank: number;
  chunk_id: string;
  article_id: string | null;
  section: string | null;
  score: number;
  text: string;
}

export interface AskResponse {
  answer: string;
  chunks: ChunkResult[];
  retrieval_ms: number;
  generation_ms: number;
  total_ms: number;
  citations_valid: boolean;
  retriever: string;
  trace_id?: string | null;
}

export interface Message {
  role: 'user' | 'assistant';
  text: string;
  response?: AskResponse;
}

export interface FeedbackReason {
  code: string;
  label: string;
}

export interface FeedbackPayload {
  trace_id: string;
  rating: 'up' | 'down';
  reason_code?: string;
  comment?: string;
}

/** Where the chat front desk sends a question (POST /api/chat/route). */
export interface RouteDecision {
  route: 'agent' | 'docs';
  source: 'code' | 'rule' | 'llm' | 'fallback';
  reason: string;
  needs_account: boolean;
}

@Injectable({ providedIn: 'root' })
export class ChatService {
  private readonly apiUrl = '/api/ask';

  constructor(private http: HttpClient) {}

  ask(question: string, useHybrid: boolean = true): Observable<AskResponse> {
    return this.http.post<AskResponse>(this.apiUrl, { question, use_hybrid: useHybrid });
  }

  route(text: string, customerId?: string): Observable<RouteDecision> {
    return this.http.post<RouteDecision>('/api/chat/route', { text, customer_id: customerId });
  }

  feedbackReasons(): Observable<FeedbackReason[]> {
    return this.http.get<FeedbackReason[]>('/api/feedback/reasons');
  }

  sendFeedback(payload: FeedbackPayload): Observable<{ saved: boolean; rating: string }> {
    return this.http.post<{ saved: boolean; rating: string }>('/api/feedback', payload);
  }
}
