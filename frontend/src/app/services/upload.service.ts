import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface UploadResponse {
  filename: string;
  chunks_indexed: number;
  collection: string;
  status: string;
}

@Injectable({ providedIn: 'root' })
export class UploadService {
  private readonly apiUrl = '/api/upload';

  constructor(private http: HttpClient) {}

  uploadDocument(file: File): Observable<UploadResponse> {
    const form = new FormData();
    form.append('file', file, file.name);
    return this.http.post<UploadResponse>(this.apiUrl, form);
  }
}
