import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, tap } from 'rxjs';

export interface AuthUser {
  email: string;
  role: 'admin' | 'user';
}

const TOKEN_KEY = 'auth_token';
const USER_KEY = 'auth_user';

function decodeJwtExpiry(token: string): number | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return typeof payload.exp === 'number' ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

function isTokenExpired(token: string): boolean {
  const exp = decodeJwtExpiry(token);
  if (exp === null) return true;
  return Date.now() >= exp - 30_000; // 30s grace period
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private _user$ = new BehaviorSubject<AuthUser | null>(this._loadFromStorage());

  readonly user$ = this._user$.asObservable();

  constructor(private http: HttpClient) {}

  private _loadFromStorage(): AuthUser | null {
    try {
      const token = localStorage.getItem(TOKEN_KEY);
      const raw = localStorage.getItem(USER_KEY);
      if (!token || !raw || isTokenExpired(token)) {
        this._clearStorage();
        return null;
      }
      return JSON.parse(raw) as AuthUser;
    } catch {
      this._clearStorage();
      return null;
    }
  }

  private _clearStorage(): void {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  get token(): string | null {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token && isTokenExpired(token)) {
      this.logout();
      return null;
    }
    return token;
  }

  get currentUser(): AuthUser | null {
    return this._user$.value;
  }

  get isLoggedIn(): boolean {
    return !!this.token && !!this._user$.value;
  }

  get isAdmin(): boolean {
    return this._user$.value?.role === 'admin';
  }

  loginWithGoogle(credential: string): Observable<{ token: string; user: AuthUser }> {
    return this.http
      .post<{ token: string; user: AuthUser }>('/api/auth/google', { credential })
      .pipe(tap(res => this._store(res)));
  }

  authConfig(): Observable<{ google_client_id: string; password_auth_enabled: boolean }> {
    return this.http.get<{ google_client_id: string; password_auth_enabled: boolean }>('/api/auth/config');
  }

  loginWithPassword(email: string, password: string): Observable<{ token: string; user: AuthUser }> {
    return this.http.post<{ token: string; user: AuthUser }>('/api/auth/login', { email, password })
      .pipe(tap(res => this._store(res)));
  }

  register(email: string, password: string, fullName: string): Observable<{ token: string; user: AuthUser }> {
    return this.http.post<{ token: string; user: AuthUser }>('/api/auth/register',
      { email, password, full_name: fullName }).pipe(tap(res => this._store(res)));
  }

  private _store(res: { token: string; user: AuthUser }): void {
    localStorage.setItem(TOKEN_KEY, res.token);
    localStorage.setItem(USER_KEY, JSON.stringify(res.user));
    this._user$.next(res.user);
  }

  logout(): void {
    this._clearStorage();
    this._user$.next(null);
  }
}
