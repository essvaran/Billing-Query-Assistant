import { Component, OnInit, NgZone } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { safeReturnUrl } from '../../interceptors/auth.interceptor';
import { AuthService } from '../../services/auth.service';
import { environment } from '../../../environments/environment';

declare const google: {
  accounts: {
    id: {
      initialize(config: object): void;
      renderButton(element: HTMLElement, config: object): void;
    };
  };
};

const GSI_LOAD_TIMEOUT_MS = 10_000;
// The same rules the API applies (api/auth.py), so a form that passes here is not rejected there.
const EMAIL_PATTERN = /^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$/;
const PASSWORD_MIN = 8;
const PASSWORD_MAX_BYTES = 72;   // bcrypt's limit; an accented or non-Latin character takes 2 to 4 bytes
const NAME_MAX = 120;
const EMAIL_MAX = 254;

type Field = 'fullName' | 'email' | 'password';
export type FieldErrors = Partial<Record<Field, string>>;

/** Field-level checks for the sign-in and sign-up form; an empty object means the form can be sent. */
export function validateLogin(mode: 'signin' | 'signup', fullName: string, email: string, password: string): FieldErrors {
  const errors: FieldErrors = {};
  if (mode === 'signup') {
    const name = fullName.trim();
    if (!name) errors.fullName = 'Enter your full name.';
    else if (name.length > NAME_MAX) errors.fullName = `Use at most ${NAME_MAX} characters.`;
  }
  const mail = email.trim();
  if (!mail) errors.email = 'Enter your email address.';
  else if (mail.length > EMAIL_MAX || !EMAIL_PATTERN.test(mail)) errors.email = 'Enter a valid email address, like name@example.com.';
  if (!password) errors.password = 'Enter your password.';
  else if (mode === 'signup' && password.length < PASSWORD_MIN) errors.password = `Use at least ${PASSWORD_MIN} characters.`;
  else if (mode === 'signup' && new TextEncoder().encode(password).length > PASSWORD_MAX_BYTES) {
    errors.password = 'This password is too long. Use a shorter one (accented and non-Latin characters count double or more).';
  }
  return errors;
}

/** Google's sign-in script is needed only on this page, so it loads here instead of on every page. */
function loadGoogleScript(): void {
  if (document.querySelector('script[data-gsi]')) return;
  const script = document.createElement('script');
  script.src = 'https://accounts.google.com/gsi/client';
  script.async = true;
  script.defer = true;
  script.dataset['gsi'] = 'true';
  document.head.appendChild(script);
}

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="login-shell">
      <div class="login-card">
        <div class="login-logo">
          <span class="logo-icon">⚡</span>
          <h1 class="login-title">Billing Support</h1>
          <p class="login-subtitle">{{ mode === 'signin' ? 'Sign in to continue' : 'Create your account' }}</p>
        </div>

        @if (sessionExpired) {
          <div class="login-notice" role="status">Your session expired. Please sign in again.</div>
        }
        @if (accountDisabled) {
          <div class="login-notice" role="alert">This account has been disabled. Contact support if you think this is a mistake.</div>
        }

        @if (passwordAuth) {
          <div class="mode-tabs" role="tablist">
            <button type="button" role="tab" [class.active]="mode === 'signin'" [attr.aria-selected]="mode === 'signin'"
                    (click)="setMode('signin')">Sign in</button>
            <button type="button" role="tab" [class.active]="mode === 'signup'" [attr.aria-selected]="mode === 'signup'"
                    (click)="setMode('signup')">Create account</button>
          </div>

          <form class="login-form" (ngSubmit)="submit()" novalidate>
            @if (mode === 'signup') {
              <label class="t1-label" for="full_name">Full name</label>
              <input id="full_name" class="t1-input" name="full_name" [(ngModel)]="fullName" (ngModelChange)="edited()"
                     (blur)="touch('fullName')" autocomplete="name" required
                     [class.invalid]="show('fullName')" [attr.aria-invalid]="show('fullName')"
                     [attr.aria-describedby]="show('fullName') ? 'full_name-error' : null" />
              @if (show('fullName')) { <span id="full_name-error" class="field-error">{{ errors().fullName }}</span> }
            }
            <label class="t1-label" for="email">Email</label>
            <input id="email" class="t1-input" type="email" name="email" [(ngModel)]="email" (ngModelChange)="edited()"
                   (blur)="touch('email')" autocomplete="email" required
                   [class.invalid]="show('email')" [attr.aria-invalid]="show('email')"
                   [attr.aria-describedby]="show('email') ? 'email-error' : null" />
            @if (show('email')) { <span id="email-error" class="field-error">{{ errors().email }}</span> }
            <label class="t1-label" for="password">Password</label>
            <input id="password" class="t1-input" type="password" name="password" [(ngModel)]="password" (ngModelChange)="edited()"
                   (blur)="touch('password')" required
                   [attr.autocomplete]="mode === 'signin' ? 'current-password' : 'new-password'"
                   [class.invalid]="show('password')" [attr.aria-invalid]="show('password')"
                   [attr.aria-describedby]="show('password') ? 'password-error' : (mode === 'signup' ? 'password-hint' : null)" />
            @if (show('password')) {
              <span id="password-error" class="field-error">{{ errors().password }}</span>
            } @else if (mode === 'signup') {
              <span id="password-hint" class="hint">At least 8 characters.</span>
            }
            <button class="t1-btn t1-btn--primary submit" type="submit" [disabled]="busy">
              @if (busy) { <span class="spinner"></span> }
              {{ mode === 'signin' ? 'Sign in' : 'Create account' }}
            </button>
          </form>
        }

        @if (loginError) {
          <div class="login-error" role="alert">{{ loginError }}</div>
        }

        @if (googleClientId) {
          @if (passwordAuth) { <div class="or"><span>or</span></div> }
          @if (gsiLoading) {
            <div class="gsi-loader">
              <span class="spinner"></span>
              <span>Loading Google sign-in…</span>
            </div>
          }
          @if (gsiError) {
            <div class="login-error">{{ gsiError }}</div>
          }
          <div id="google-btn-container" [class.hidden]="gsiLoading || !!gsiError"></div>
        }
      </div>
    </div>
  `,
  styles: [`
    .login-shell { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: var(--surface-base); padding: 1rem; }
    .login-card {
      background: var(--surface-raised); border: 1px solid var(--border); border-radius: 16px;
      padding: 2rem; width: 100%; max-width: 400px; display: flex; flex-direction: column;
      align-items: stretch; gap: 1.1rem; box-shadow: 0 8px 40px rgba(0,0,0,0.5);
    }
    .login-logo { text-align: center; display: flex; flex-direction: column; align-items: center; gap: 0.4rem; }
    .logo-icon { font-size: 2.2rem; line-height: 1; }
    .login-title { margin: 0; font-size: 1.25rem; font-weight: 700; color: var(--text-primary); }
    .login-subtitle { margin: 0; font-size: 0.85rem; color: var(--text-muted); }
    .mode-tabs { display: grid; grid-template-columns: 1fr 1fr; border: 1px solid var(--border); border-radius: var(--radius-md); overflow: hidden; }
    .mode-tabs button { background: none; border: 0; padding: .55rem; color: var(--text-secondary); cursor: pointer; font: inherit; font-size: .85rem; }
    .mode-tabs button.active { background: var(--accent); color: var(--surface-card); font-weight: 600; }
    .login-form { display: flex; flex-direction: column; gap: .35rem; }
    .login-form .t1-input { width: 100%; box-sizing: border-box; margin-bottom: .45rem; }
    .login-form .t1-input.invalid { border-color: var(--danger); }
    .field-error { font-size: .75rem; color: var(--danger); margin-top: -.2rem; margin-bottom: .3rem; }
    .hint { font-size: .75rem; color: var(--text-muted); margin-top: -.2rem; margin-bottom: .3rem; }
    .submit { margin-top: .4rem; justify-content: center; display: inline-flex; gap: .5rem; align-items: center; }
    .or { display: flex; align-items: center; gap: .75rem; color: var(--text-muted); font-size: .75rem; }
    .or::before, .or::after { content: ''; flex: 1; height: 1px; background: var(--border); }
    #google-btn-container { display: flex; justify-content: center; width: 100%; min-height: 44px; &.hidden { display: none; } }
    .gsi-loader { display: flex; align-items: center; justify-content: center; gap: 0.6rem; color: var(--text-muted); font-size: 0.875rem; }
    .spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.7s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .login-notice {
      font-size: 0.825rem; color: var(--warning); background: rgba(250,179,135,0.1);
      border: 1px solid rgba(250,179,135,0.3); border-radius: 6px; padding: 0.5rem 0.75rem; text-align: center;
    }
    .login-error {
      color: var(--danger); font-size: 0.825rem; background: rgba(243,139,168,0.1);
      border: 1px solid rgba(243,139,168,0.3); border-radius: 6px; padding: 0.5rem 0.75rem; text-align: center;
    }
  `],
})
export class LoginComponent implements OnInit {
  mode: 'signin' | 'signup' = 'signin';
  email = '';
  password = '';
  fullName = '';
  busy = false;
  submitted = false;
  touched: Partial<Record<Field, boolean>> = {};

  passwordAuth = true;
  googleClientId = '';
  gsiLoading = true;
  gsiError: string | null = null;
  loginError: string | null = null;
  sessionExpired = false;
  accountDisabled = false;

  /** After signing in, go back to the page the person was on (same-app paths only). */
  private _afterSignIn(): void {
    const target = safeReturnUrl(this.route.snapshot.queryParamMap.get('returnUrl'));
    this.router.navigateByUrl(target ?? '/');
  }

  constructor(
    private auth: AuthService,
    private router: Router,
    private route: ActivatedRoute,
    private zone: NgZone,
  ) {}

  ngOnInit(): void {
    if (this.auth.isLoggedIn) {
      this.router.navigate(['/']);
      return;
    }
    const reason = this.route.snapshot.queryParamMap.get('reason');
    this.sessionExpired = reason === 'session_expired';
    this.accountDisabled = reason === 'disabled';
    // The server says which sign-in methods are on; if it cannot be reached, fall back to the build-time client id.
    this.auth.authConfig().subscribe({
      next: cfg => {
        this.passwordAuth = cfg.password_auth_enabled;
        this._enableGoogle(cfg.google_client_id);
      },
      error: () => this._enableGoogle(environment.googleClientId),
    });
  }

  setMode(mode: 'signin' | 'signup'): void {
    this.mode = mode;
    this.loginError = null;
    this.submitted = false;
    this.touched = {};
  }

  errors(): FieldErrors {
    return validateLogin(this.mode, this.fullName, this.email, this.password);
  }

  /** A field shows its error once the user has left it or tried to submit, not while they are still typing it. */
  show(field: Field): boolean {
    return (this.submitted || !!this.touched[field]) && !!this.errors()[field];
  }

  touch(field: Field): void {
    this.touched[field] = true;
  }

  edited(): void {
    this.loginError = null;   // a server error refers to what was sent, not to what is being typed now
  }

  submit(): void {
    this.loginError = null;
    this.submitted = true;
    const invalid = (['fullName', 'email', 'password'] as Field[]).find(f => this.errors()[f]);
    if (invalid) {
      const id = { fullName: 'full_name', email: 'email', password: 'password' }[invalid];
      document.getElementById(id)?.focus();
      return;
    }
    const email = this.email.trim();
    this.busy = true;
    const request = this.mode === 'signin'
      ? this.auth.loginWithPassword(email, this.password)
      : this.auth.register(email, this.password, this.fullName.trim());
    request.subscribe({
      next: () => { this.busy = false; this._afterSignIn(); },
      error: err => {
        this.busy = false;
        this.loginError = this._message(err);
      },
    });
  }

  private _message(err: any): string {
    if (err?.status === 429) return 'Too many attempts. Wait a minute and try again.';
    const detail = err?.error?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg; // validation errors from the API
    return 'Something went wrong. Please try again.';
  }

  private _enableGoogle(clientId: string): void {
    this.googleClientId = clientId;
    if (!clientId) return;
    loadGoogleScript();
    const deadline = Date.now() + GSI_LOAD_TIMEOUT_MS;
    const tryInit = () => {
      if (typeof google !== 'undefined') {
        this.zone.run(() => setTimeout(() => this._mountButton(clientId)));
        return;
      }
      if (Date.now() > deadline) {
        this.zone.run(() => {
          this.gsiLoading = false;
          this.gsiError = 'Google Sign-In could not load. Use email and password instead.';
        });
        return;
      }
      setTimeout(tryInit, 200);
    };
    tryInit();
  }

  private _mountButton(clientId: string): void {
    try {
      google.accounts.id.initialize({
        client_id: clientId,
        callback: (response: { credential: string }) => {
          this.zone.run(() => this._handleCredential(response.credential));
        },
      });
      const container = document.getElementById('google-btn-container');
      if (container) {
        google.accounts.id.renderButton(container, {
          theme: 'filled_black', size: 'large', shape: 'pill', text: 'signin_with', width: 280,
        });
      }
      this.gsiLoading = false;
    } catch {
      this.gsiLoading = false;
      this.gsiError = 'Failed to initialize Google Sign-In.';
    }
  }

  private _handleCredential(credential: string): void {
    this.loginError = null;
    this.auth.loginWithGoogle(credential).subscribe({
      next: () => this._afterSignIn(),
      error: err => { this.loginError = this._message(err); },
    });
  }
}
