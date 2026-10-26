import { ChangeDetectionStrategy, Component, Injectable, inject, signal } from '@angular/core';
import { ModalComponent } from './modal.component';

export interface ConfirmOptions {
  title?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Styles the confirm button as destructive (delete, void, disable). */
  danger?: boolean;
}

interface Pending extends Required<ConfirmOptions> { message: string; resolve: (ok: boolean) => void }

/**
 * App-styled confirmation in place of window.confirm: same look in every theme, focus trapped, Escape cancels,
 * and focus returns to the button that asked. `await confirm.ask('Delete X?')` resolves true only on confirm.
 */
@Injectable({ providedIn: 'root' })
export class ConfirmService {
  readonly pending = signal<Pending | null>(null);

  ask(message: string, options: ConfirmOptions = {}): Promise<boolean> {
    this.pending()?.resolve(false);           // a second question cancels the first
    return new Promise<boolean>(resolve => {
      this.pending.set({
        message, resolve,
        title: options.title ?? 'Please confirm',
        confirmLabel: options.confirmLabel ?? 'Confirm',
        cancelLabel: options.cancelLabel ?? 'Cancel',
        danger: options.danger ?? false,
      });
    });
  }

  answer(ok: boolean): void {
    const p = this.pending();
    this.pending.set(null);
    p?.resolve(ok);
  }
}

@Component({
  selector: 'app-confirm-host',
  standalone: true,
  imports: [ModalComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (svc.pending(); as p) {
      <app-modal [title]="p.title" (closed)="svc.answer(false)">
        <p class="confirm__msg">{{ p.message }}</p>
        <ng-container modal-actions>
          <button type="button" class="t1-btn" (click)="svc.answer(false)">{{ p.cancelLabel }}</button>
          <button type="button" class="t1-btn" [class.t1-btn--danger]="p.danger" [class.t1-btn--primary]="!p.danger"
                  (click)="svc.answer(true)">{{ p.confirmLabel }}</button>
        </ng-container>
      </app-modal>
    }`,
  styles: [`.confirm__msg { margin: 0; font-size: .9rem; line-height: 1.5; }`],
})
export class ConfirmHostComponent {
  svc = inject(ConfirmService);
}
