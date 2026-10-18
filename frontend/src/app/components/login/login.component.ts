import { Component, OnInit, NgZone } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
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
          <div class="login-notice">Your session expired — please sign in again.</div>
        }

        @if (passwordAuth) {
          <div class="mode-tabs" role="tablist">
            <button type="button" role="tab" [class.active]="mode === 'signin'" [attr.aria-selected]="mode === 'signin'"
                    (click)="setMode('signin')">Sign in</button>
            <button type="button" role="tab" [class.active]="mode === 'signup'" [attr.aria-selected]="mode === 'signup'"
                    (click)="setMode('signup')">Create account</button>
          </div>

          <form class="login-form" (ngSubmit)="submit()" #f="ngForm" novalidate>
            @if (mode === 'signup') {
              <label class="t1-label" for="full_name">Full name</label>
              <input id="full_name" class="t1-input" name="full_name" [(ngModel)]="fullName" required
                     autocomplete="name" maxlength="120" />
            }
            <label class="t1-label" for="email">Email</label>
            <input id="email" class="t1-input" type="email" name="email" [(ngModel)]="email" required
                   autocomplete="email" maxlength="254" />
            <label class="t1-label" for="password">Password</label>
            <input id="password" class="t1-input" type="password" name="password" [(ngModel)]="password" required
                   [attr.autocomplete]="mode === 'signin' ? 'current-password' : 'new-password'"
                   [minlength]="mode === 'signup' ? 8 : 1" maxlength="72" />
            @if (mode === 'signup') { <span class="hint">At least 8 characters.</span> }
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

  passwordAuth = true;
  googleClientId = '';
  gsiLoading = true;
  gsiError: string | null = null;
  loginError: string | null = null;
  sessionExpired = false;

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
    this.sessionExpired = this.route.snapshot.queryParamMap.get('reason') === 'session_expired';
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
  }

  submit(): void {
    this.loginError = null;
    const email = this.email.trim();
    if (!email || !this.password || (this.mode === 'signup' && !this.fullName.trim())) {
      this.loginError = 'Fill in every field.';
      return;
    }
    if (this.mode === 'signup' && this.password.length < 8) {
      this.loginError = 'Use a password of at least 8 characters.';
      return;
    }
    this.busy = true;
    const request = this.mode === 'signin'
      ? this.auth.loginWithPassword(email, this.password)
      : this.auth.register(email, this.password, this.fullName.trim());
    request.subscribe({
      next: () => { this.busy = false; this.router.navigate(['/']); },
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
      next: () => this.router.navigate(['/']),
      error: err => { this.loginError = this._message(err); },
    });
  }
}
