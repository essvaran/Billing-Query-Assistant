import { Component, OnInit, NgZone } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { CommonModule } from '@angular/common';
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
  imports: [CommonModule],
  template: `
    <div class="login-shell">
      <div class="login-card">
        <div class="login-logo">
          <span class="logo-icon">⚡</span>
          <h1 class="login-title">Billing Support RAG</h1>
          <p class="login-subtitle">Sign in to continue</p>
        </div>

        <div class="divider"></div>

        @if (sessionExpired) {
          <div class="login-notice">Your session expired — please sign in again.</div>
        }

        @if (gsiLoading) {
          <div class="gsi-loader">
            <span class="spinner"></span>
            <span>Loading sign-in…</span>
          </div>
        }

        @if (gsiError) {
          <div class="login-error">{{ gsiError }}</div>
        }

        <div id="google-btn-container" [class.hidden]="gsiLoading || !!gsiError"></div>

        @if (loginError) {
          <div class="login-error">{{ loginError }}</div>
        }
      </div>
    </div>
  `,
  styles: [`
    .login-shell {
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: var(--surface-base);
    }
    .login-card {
      background: var(--surface-raised);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 2.5rem 2rem;
      width: 100%;
      max-width: 380px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 1.5rem;
      box-shadow: 0 8px 40px rgba(0,0,0,0.5);
    }
    .login-logo {
      text-align: center;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.5rem;
    }
    .logo-icon { font-size: 2.5rem; line-height: 1; }
    .login-title {
      margin: 0;
      font-size: 1.25rem;
      font-weight: 700;
      color: var(--text-primary);
      letter-spacing: 0.01em;
    }
    .login-subtitle { margin: 0; font-size: 0.85rem; color: var(--text-muted); }
    .divider { width: 100%; height: 1px; background: var(--border); }
    #google-btn-container {
      display: flex;
      justify-content: center;
      width: 100%;
      min-height: 44px;
      &.hidden { display: none; }
    }
    .gsi-loader {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      color: var(--text-muted);
      font-size: 0.875rem;
    }
    .spinner {
      display: inline-block;
      width: 16px;
      height: 16px;
      border: 2px solid var(--border);
      border-top-color: var(--accent);
      border-radius: 50%;
      animation: spin 0.7s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .login-notice {
      font-size: 0.825rem;
      color: var(--warning);
      background: rgba(250,179,135,0.1);
      border: 1px solid rgba(250,179,135,0.3);
      border-radius: 6px;
      padding: 0.5rem 0.75rem;
      width: 100%;
      box-sizing: border-box;
      text-align: center;
    }
    .login-error {
      color: var(--danger);
      font-size: 0.825rem;
      background: rgba(243,139,168,0.1);
      border: 1px solid rgba(243,139,168,0.3);
      border-radius: 6px;
      padding: 0.5rem 0.75rem;
      width: 100%;
      box-sizing: border-box;
      text-align: center;
    }
  `],
})
export class LoginComponent implements OnInit {
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
    this._initGoogle();
  }

  private _initGoogle(): void {
    const deadline = Date.now() + GSI_LOAD_TIMEOUT_MS;

    const tryInit = () => {
      if (typeof google !== 'undefined') {
        this._mountButton();
        return;
      }
      if (Date.now() > deadline) {
        this.zone.run(() => {
          this.gsiLoading = false;
          this.gsiError = 'Google Sign-In could not load. Check your internet connection or ad-blocker settings.';
        });
        return;
      }
      setTimeout(tryInit, 200);
    };

    tryInit();
  }

  private _mountButton(): void {
    try {
      google.accounts.id.initialize({
        client_id: environment.googleClientId,
        callback: (response: { credential: string }) => {
          this.zone.run(() => this._handleCredential(response.credential));
        },
      });
      const container = document.getElementById('google-btn-container');
      if (container) {
        google.accounts.id.renderButton(container, {
          theme: 'filled_black',
          size: 'large',
          shape: 'pill',
          text: 'signin_with',
          width: 280,
        });
      }
      this.zone.run(() => (this.gsiLoading = false));
    } catch (err) {
      this.zone.run(() => {
        this.gsiLoading = false;
        this.gsiError = 'Failed to initialize Google Sign-In.';
      });
    }
  }

  private _handleCredential(credential: string): void {
    this.loginError = null;
    this.auth.loginWithGoogle(credential).subscribe({
      next: () => this.router.navigate(['/']),
      error: err => {
        this.loginError = err?.error?.detail ?? 'Sign-in failed — please try again.';
      },
    });
  }
}
