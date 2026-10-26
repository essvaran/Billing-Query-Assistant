import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '../services/auth.service';

export const authGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (auth.isLoggedIn) return true;
  // remember where the person was going, so signing in takes them there instead of the home page
  const returnUrl = state?.url && state.url !== '/' ? state.url : null;
  return router.createUrlTree(['/login'], returnUrl ? { queryParams: { returnUrl } } : {});
};
