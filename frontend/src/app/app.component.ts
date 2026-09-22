import { Component, OnDestroy } from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';
import { filter } from 'rxjs/operators';
import { AuthService } from './services/auth.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, CommonModule],
  template: `
    @if (showNav) {
      <nav class="nav" role="navigation" aria-label="Main navigation">
        <a class="nav__brand" routerLink="/" aria-label="Billing Support RAG home">
          <span class="nav__brand-icon">⚡</span>
          <span class="nav__brand-text">Billing Support</span>
        </a>

        <div class="nav__links" role="menubar">
          <a class="nav__link" routerLink="/" routerLinkActive="nav__link--active"
             [routerLinkActiveOptions]="{exact:true}" role="menuitem">Chat</a>
          <a class="nav__link" routerLink="/agent-chat" routerLinkActive="nav__link--active" role="menuitem">Agent</a>
          <a class="nav__link" routerLink="/traces" routerLinkActive="nav__link--active" role="menuitem">Traces</a>
          <a class="nav__link" routerLink="/sample" routerLinkActive="nav__link--active" role="menuitem">Sample</a>
          <a class="nav__link" routerLink="/taxonomy" routerLinkActive="nav__link--active" role="menuitem">Taxonomy</a>
          <a class="nav__link" routerLink="/eval" routerLinkActive="nav__link--active" role="menuitem">Eval</a>
          <a class="nav__link" routerLink="/race" routerLinkActive="nav__link--active" role="menuitem">Race</a>
          <a class="nav__link" routerLink="/trajectory" routerLinkActive="nav__link--active" role="menuitem">Trajectory</a>
          @if (isAdmin) {
            <a class="nav__link nav__link--admin" routerLink="/admin"
               routerLinkActive="nav__link--active" role="menuitem">Admin</a>
          }
        </div>

        <div class="nav__user">
          <span class="role-chip" [class.role-chip--admin]="isAdmin">
            {{ isAdmin ? 'Admin' : 'User' }}
          </span>
          <span class="nav__email" [title]="userEmail">{{ userEmail }}</span>
          <button class="nav__signout" (click)="logout()" aria-label="Sign out">
            Sign out
          </button>
        </div>
      </nav>
    }
    <main>
      <router-outlet />
    </main>
  `,
  styles: [`
    :host { display: block; }

    .nav {
      display: flex;
      align-items: center;
      gap: 0;
      padding: 0 1.5rem;
      height: 52px;
      background: var(--surface-raised);
      border-bottom: 1px solid var(--border);
      position: sticky;
      top: 0;
      z-index: 100;
    }

    .nav__brand {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      text-decoration: none;
      margin-right: 1.5rem;
      flex-shrink: 0;
    }
    .nav__brand-icon { font-size: 1.1rem; }
    .nav__brand-text {
      font-weight: 700;
      font-size: 0.9rem;
      color: var(--text-primary);
      letter-spacing: 0.01em;
      white-space: nowrap;
    }

    .nav__links {
      display: flex;
      align-items: center;
      gap: 0.125rem;
      flex: 1;
      overflow-x: auto;
      scrollbar-width: none;
      &::-webkit-scrollbar { display: none; }
    }

    .nav__link {
      color: var(--text-muted);
      text-decoration: none;
      font-size: 0.825rem;
      font-weight: 500;
      padding: 0.35rem 0.7rem;
      border-radius: var(--radius-md);
      transition: background var(--transition), color var(--transition);
      white-space: nowrap;
      &:hover {
        background: var(--border);
        color: var(--text-primary);
        text-decoration: none;
      }
      &--active {
        background: rgba(137,180,250,0.12);
        color: var(--accent);
      }
      &--admin {
        color: var(--purple);
        &.nav__link--active { background: rgba(203,166,247,0.12); }
      }
    }

    .nav__user {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      margin-left: 1rem;
      flex-shrink: 0;
    }

    .role-chip {
      font-size: 0.68rem;
      font-weight: 700;
      padding: 0.15rem 0.5rem;
      border-radius: var(--radius-sm);
      background: rgba(108,112,134,0.25);
      color: var(--text-secondary);
      letter-spacing: 0.04em;
      text-transform: uppercase;
      &--admin {
        background: rgba(203,166,247,0.18);
        color: var(--purple);
      }
    }

    .nav__email {
      font-size: 0.78rem;
      color: var(--text-muted);
      max-width: 160px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .nav__signout {
      padding: 0.3rem 0.7rem;
      background: none;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      color: var(--text-muted);
      font-size: 0.78rem;
      cursor: pointer;
      font-family: inherit;
      transition: border-color var(--transition), color var(--transition);
      white-space: nowrap;
      &:hover {
        border-color: var(--danger);
        color: var(--danger);
      }
    }

    main { min-height: calc(100vh - 52px); }
  `],
})
export class AppComponent implements OnDestroy {
  showNav = true;
  private _sub: Subscription;

  constructor(public auth: AuthService, private router: Router) {
    this._sub = this.router.events.pipe(
      filter((e): e is NavigationEnd => e instanceof NavigationEnd),
    ).subscribe(e => {
      this.showNav = !e.urlAfterRedirects.startsWith('/login');
    });
  }

  ngOnDestroy(): void {
    this._sub.unsubscribe();
  }

  get isAdmin(): boolean { return this.auth.isAdmin; }
  get userEmail(): string { return this.auth.currentUser?.email ?? ''; }

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}
