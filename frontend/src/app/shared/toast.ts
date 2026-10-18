import { ChangeDetectionStrategy, Component, Injectable, inject, signal } from '@angular/core';

export interface Toast { id: number; message: string; tone: 'info' | 'success' | 'error' }

@Injectable({ providedIn: 'root' })
export class ToastService {
  readonly toasts = signal<Toast[]>([]);
  private next = 1;

  show(message: string, tone: Toast['tone'] = 'info', ms = 4500): void {
    const id = this.next++;
    this.toasts.update(list => [...list, { id, message, tone }]);
    setTimeout(() => this.dismiss(id), ms);
  }
  success(message: string): void { this.show(message, 'success'); }
  error(message: string): void { this.show(message, 'error', 8000); }
  dismiss(id: number): void { this.toasts.update(list => list.filter(t => t.id !== id)); }
}

/** One live region for the whole app: screen readers hear each toast politely. */
@Component({
  selector: 'app-toast-host',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="host" aria-live="polite" aria-atomic="false">
      @for (t of svc.toasts(); track t.id) {
        <div class="toast" [attr.data-tone]="t.tone" role="status">
          <span>{{ t.message }}</span>
          <button type="button" class="toast__x" (click)="svc.dismiss(t.id)" aria-label="Dismiss notification">Close</button>
        </div>
      }
    </div>`,
  styles: [`
    .host { position: fixed; right: 1rem; bottom: 1rem; display: flex; flex-direction: column; gap: .5rem; z-index: 1000; max-width: min(24rem, calc(100vw - 2rem)); }
    .toast { display: flex; gap: .75rem; align-items: center; justify-content: space-between; padding: .65rem .85rem;
      border-radius: var(--radius-md); background: var(--surface-overlay); border: 1px solid var(--border-strong);
      box-shadow: var(--shadow-md); font-size: .85rem; }
    .toast[data-tone='success'] { border-color: rgba(166,227,161,.5); }
    .toast[data-tone='error'] { border-color: rgba(243,139,168,.6); }
    .toast__x { background: none; border: 0; color: var(--text-muted); cursor: pointer; font: inherit; font-size: .75rem; }
    .toast__x:hover { color: var(--text-primary); }
  `],
})
export class ToastHostComponent {
  svc = inject(ToastService);
}
