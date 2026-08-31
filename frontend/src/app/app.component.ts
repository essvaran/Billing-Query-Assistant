import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <nav class="app-nav">
      <span class="app-nav__brand">Billing Support RAG</span>
      <a class="app-nav__link" routerLink="/" routerLinkActive="app-nav__link--active"
         [routerLinkActiveOptions]="{exact: true}">Chat</a>
      <a class="app-nav__link" routerLink="/traces" routerLinkActive="app-nav__link--active">Traces</a>
      <a class="app-nav__link" routerLink="/sample" routerLinkActive="app-nav__link--active">Sample</a>
      <a class="app-nav__link" routerLink="/taxonomy" routerLinkActive="app-nav__link--active">Taxonomy</a>
    </nav>
    <router-outlet />
  `,
  styles: [`
    .app-nav {
      display: flex;
      align-items: center;
      gap: 1.5rem;
      padding: 0.75rem 1.5rem;
      background: #1e1e2e;
      border-bottom: 1px solid #313244;
    }
    .app-nav__brand {
      font-weight: 600;
      color: #cdd6f4;
      font-size: 0.9rem;
      letter-spacing: 0.02em;
      margin-right: auto;
    }
    .app-nav__link {
      color: #a6adc8;
      text-decoration: none;
      font-size: 0.875rem;
      padding: 0.25rem 0.75rem;
      border-radius: 6px;
      transition: background 0.15s, color 0.15s;
    }
    .app-nav__link:hover {
      background: #313244;
      color: #cdd6f4;
    }
    .app-nav__link--active {
      background: #313244;
      color: #89b4fa;
    }
  `],
})
export class AppComponent {}
