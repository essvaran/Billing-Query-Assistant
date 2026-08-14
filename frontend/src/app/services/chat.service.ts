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
}

export interface Message {
  role: 'user' | 'assistant';
  text: string;
  response?: AskResponse;
}

@Injectable({ providedIn: 'root' })
export class ChatService {
  private readonly apiUrl = '/api/ask';

  constructor(private http: HttpClient) {}

  ask(question: string): Observable<AskResponse> {
    return this.http.post<AskResponse>(this.apiUrl, { question });
  }
}
