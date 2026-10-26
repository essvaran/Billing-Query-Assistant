import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { AuthService } from '../services/auth.service';

/** Sign-in calls answer 401 for a wrong password; that is a form error, not an expired session. */
const SIGN_IN_CALLS = ['/api/auth/login', '/api/auth/register', '/api/auth/google', '/api/auth/config'];
export const DISABLED_DETAIL = 'This account has been disabled';

/** Only a same-app path may be a return address, never another site ("//evil.example" or "https://..."). */
export function safeReturnUrl(url: string | null | undefined): string | null {
  if (!url || !url.startsWith('/') || url.startsWith('//') || url.startsWith('/login')) return null;
  return url;
}

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  const token = auth.token;
  const authReq = token
    ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
    : req;
  const signInCall = SIGN_IN_CALLS.some(path => req.url.startsWith(path));

  return next(authReq).pipe(
    catchError(err => {
      if (!signInCall && err.status === 401) {
        const returnUrl = safeReturnUrl(router.url);
        auth.logout();
        router.navigate(['/login'], { queryParams: { reason: 'session_expired', ...(returnUrl ? { returnUrl } : {}) } });
      } else if (!signInCall && err.status === 403 && err.error?.detail === DISABLED_DETAIL) {
        auth.logout();
        router.navigate(['/login'], { queryParams: { reason: 'disabled' } });
      }
      // any other 403 is handled per call site; just propagate
      return throwError(() => err);
    }),
  );
};
