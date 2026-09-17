import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-not-found',
  standalone: true,
  imports: [RouterLink],
  template: `
    <div class="nf-shell">
      <span class="nf-code">404</span>
      <h1 class="nf-title">Page not found</h1>
      <p class="nf-desc">The page you are looking for does not exist.</p>
      <a class="nf-btn" routerLink="/">Go home</a>
    </div>
  `,
  styles: [`
    .nf-shell {
      min-height: 80vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 1rem;
      text-align: center;
      background: var(--surface-base);
    }
    .nf-code {
      font-size: 5rem;
      font-weight: 800;
      color: var(--border-strong);
      line-height: 1;
      letter-spacing: -0.04em;
    }
    .nf-title {
      margin: 0;
      font-size: 1.5rem;
      font-weight: 600;
      color: var(--text-primary);
    }
    .nf-desc { margin: 0; color: var(--text-muted); font-size: 0.9rem; }
    .nf-btn {
      margin-top: 0.5rem;
      padding: 0.5rem 1.5rem;
      background: var(--accent);
      color: var(--surface-base);
      border-radius: 8px;
      text-decoration: none;
      font-weight: 600;
      font-size: 0.875rem;
      transition: opacity 0.15s;
      &:hover { opacity: 0.85; }
    }
  `],
})
export class NotFoundComponent {}
