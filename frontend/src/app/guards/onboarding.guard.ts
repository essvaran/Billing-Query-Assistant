import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { AccountService } from '../services/account.service';
import { AuthService } from '../services/auth.service';

/** Signed-in customers without a live subscription pick a plan before they reach the chat. Admins skip it. */
export const onboardingGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (!auth.isLoggedIn) return router.createUrlTree(['/login']);
  if (auth.isAdmin) return true;
  return inject(AccountService).subscription().pipe(
    map(sub => (sub && sub.status !== 'cancelled') ? true : router.createUrlTree(['/onboarding'])),
    catchError(() => of(true)), // a failed lookup must not lock people out of the chat; the API enforces access
  );
};
