import { Component, inject } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

@Component({
  selector: 'app-not-found',
  standalone: true,
  imports: [RouterLink],
  template: `
    <div class="nf-shell">
      <span class="nf-code">{{ code }}</span>
      <h1 class="nf-title">{{ title }}</h1>
      <p class="nf-desc">{{ desc }}</p>
      <a class="nf-btn" routerLink="/">Go to the chat</a>
      <a class="nf-help" routerLink="/help">How to use this app</a>
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
    .nf-desc { margin: 0; color: var(--text-muted); font-size: 0.9rem; max-width: 32rem; padding: 0 1rem; }
    .nf-help { color: var(--accent); font-size: 0.85rem; }
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
export class NotFoundComponent {
  /** Also serves the "no access" page: the route passes code, title and desc in its data. */
  private data = inject(ActivatedRoute).snapshot.data;
  code = this.data['code'] ?? '404';
  title = this.data['title'] ?? 'Page not found';
  desc = this.data['desc'] ?? 'The page you are looking for does not exist.';
}
