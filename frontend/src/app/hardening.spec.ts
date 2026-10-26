import { TestBed } from '@angular/core/testing';
import { HttpClient, HttpErrorResponse, HttpHeaders, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Router, provideRouter } from '@angular/router';
import { authInterceptor, safeReturnUrl, DISABLED_DETAIL } from './interceptors/auth.interceptor';
import { authGuard } from './guards/auth.guard';
import { AuthService } from './services/auth.service';
import { Step } from './services/tier1.service';
import { StepTimelineComponent } from './shared/step-timeline.component';
import { ConfirmService } from './shared/confirm';
import { requestIdOf } from './shared/toast';
import { articleTitle } from './shared/labels';
import { loadSeedRefData } from '../testing/seed-ref-data';

beforeAll(() => loadSeedRefData());

/** A signed-in session that has not expired, so the interceptor attaches it and the guard lets it through. */
function signIn(): void {
  const payload = btoa(JSON.stringify({ sub: 'ann@example.com', exp: Math.floor(Date.now() / 1000) + 3600 }));
  localStorage.setItem('auth_token', `x.${payload}.y`);
  localStorage.setItem('auth_user', JSON.stringify({ email: 'ann@example.com', role: 'user' }));
}

describe('auth interceptor', () => {
  let http: HttpClient;
  let ctl: HttpTestingController;
  let router: Router;

  beforeEach(() => {
    signIn();
    TestBed.configureTestingModule({
      providers: [provideRouter([]), provideHttpClient(withInterceptors([authInterceptor])), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpClient);
    ctl = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    spyOn(router, 'navigate').and.resolveTo(true);
  });
  afterEach(() => localStorage.clear());

  it('treats a wrong password as a form error, not an expired session', () => {
    http.post('/api/auth/login', {}).subscribe({ error: () => undefined });
    ctl.expectOne('/api/auth/login').flush({ detail: 'Invalid email or password' }, { status: 401, statusText: 'Unauthorized' });
    expect(router.navigate).not.toHaveBeenCalled();
    expect(TestBed.inject(AuthService).isLoggedIn).toBeTrue();
  });

  it('signs out and asks to sign in again when a session expires elsewhere', () => {
    http.get('/api/account/subscription').subscribe({ error: () => undefined });
    ctl.expectOne('/api/account/subscription').flush({}, { status: 401, statusText: 'Unauthorized' });
    expect(router.navigate).toHaveBeenCalledWith(['/login'], jasmine.objectContaining({
      queryParams: jasmine.objectContaining({ reason: 'session_expired' }) }));
    expect(TestBed.inject(AuthService).isLoggedIn).toBeFalse();
  });

  it('signs a disabled account out instead of leaving it on failing pages', () => {
    http.get('/api/tier1/me/customer').subscribe({ error: () => undefined });
    ctl.expectOne('/api/tier1/me/customer').flush({ detail: DISABLED_DETAIL }, { status: 403, statusText: 'Forbidden' });
    expect(router.navigate).toHaveBeenCalledWith(['/login'], { queryParams: { reason: 'disabled' } });
  });

  it('leaves other 403s to the page that made the call', () => {
    http.get('/api/admin/users').subscribe({ error: () => undefined });
    ctl.expectOne('/api/admin/users').flush({ detail: 'Admin access required' }, { status: 403, statusText: 'Forbidden' });
    expect(router.navigate).not.toHaveBeenCalled();
  });
});

describe('return address after sign-in', () => {
  it('accepts only paths inside this app', () => {
    expect(safeReturnUrl('/account')).toBe('/account');
    expect(safeReturnUrl('//evil.example/x')).toBeNull();
    expect(safeReturnUrl('https://evil.example')).toBeNull();
    expect(safeReturnUrl('/login?x=1')).toBeNull();
    expect(safeReturnUrl(null)).toBeNull();
  });

  it('the guard remembers where a signed-out person was going', () => {
    localStorage.clear();
    TestBed.configureTestingModule({ providers: [provideRouter([]), provideHttpClient()] });
    const tree = TestBed.runInInjectionContext(() => authGuard({} as never, { url: '/account' } as never));
    expect(TestBed.inject(Router).serializeUrl(tree as never)).toBe('/login?returnUrl=%2Faccount');
  });
});

describe('StepTimelineComponent for a customer', () => {
  const steps: Step[] = [
    { type: 'guard', stage: 'pre', blocked: false, category: 'legal_threat' },
    { type: 'tool_call', lap: 1, tool: 'check_entitlement' },
    { type: 'tool_result', lap: 1, tool: 'check_entitlement', result: { policy_version: 'refund-14d', refund_days: 14 } },
    { type: 'guard', stage: 'post', violations: ['uncited_policy'], citations: 0 },
    { type: 'budget_hit', budget: 'max_laps' },
  ];

  function render(audience: 'customer' | 'admin'): string {
    TestBed.configureTestingModule({ imports: [StepTimelineComponent] });
    const fixture = TestBed.createComponent(StepTimelineComponent);
    fixture.componentRef.setInput('steps', steps);
    fixture.componentRef.setInput('audience', audience);
    fixture.detectChanges();
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  it('shows which checks ran, never codes, limits or policy internals', () => {
    const text = render('customer');
    expect(text).toContain('Sent to a person to review');
    for (const internal of ['uncited', 'max_laps', 'max laps', 'refund-14d', '14-day window', 'legal']) {
      expect(text).not.toContain(internal);
    }
  });

  it('keeps the full detail for the support team', () => {
    expect(render('admin')).toContain('uncited policy');
  });
});

describe('ConfirmService', () => {
  it('resolves true only on confirm, and a new question cancels the old one', async () => {
    const svc = new ConfirmService();
    const first = svc.ask('Delete A?');
    const second = svc.ask('Delete B?', { danger: true });
    expect(await first).toBeFalse();
    expect(svc.pending()?.message).toBe('Delete B?');
    svc.answer(true);
    expect(await second).toBeTrue();
    expect(svc.pending()).toBeNull();
  });
});

describe('customer-facing labels', () => {
  it('turns slugs into titles and finds the request id of a failed call', () => {
    expect(articleTitle('refund-policy-30d')).toBe('Refund policy 30d');
    expect(articleTitle('article_02.pdf')).toBe('Article 02');
    expect(articleTitle('')).toBe('Help centre article');
    const fromHeader = new HttpErrorResponse({ status: 502, headers: new HttpHeaders({ 'X-Request-ID': 'abc123def456' }) });
    expect(requestIdOf(fromHeader)).toBe('abc123def456');
    expect(requestIdOf({ error: { request_id: 'body-id' } })).toBe('body-id');
    expect(requestIdOf(null)).toBeNull();
  });
});
