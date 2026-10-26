import { AfterViewInit, ChangeDetectionStrategy, Component, ElementRef, EventEmitter, HostListener, Input, OnDestroy, Output, ViewChild } from '@angular/core';

let nextModalId = 0;

/**
 * Accessible dialog: role=dialog, labelled, Escape closes, Tab stays inside, and focus returns to
 * whatever opened it. Used for escalate and report-wrong-answer; the source drawer reuses the same rules.
 */
@Component({
  selector: 'app-modal',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="backdrop" (mousedown)="onBackdrop($event)">
      <div class="dialog" #dialog role="dialog" aria-modal="true" [attr.aria-labelledby]="titleId" tabindex="-1">
        <header class="dialog__head">
          <h2 [id]="titleId" class="dialog__title">{{ title }}</h2>
          <button type="button" class="dialog__close" (click)="closed.emit()" aria-label="Close dialog">Close</button>
        </header>
        <div class="dialog__body"><ng-content /></div>
        <footer class="dialog__foot"><ng-content select="[modal-actions]" /></footer>
      </div>
    </div>`,
  styles: [`
    .backdrop { position: fixed; inset: 0; background: rgba(0,0,0,.55); display: grid; place-items: center; z-index: 900; padding: 1rem; }
    .dialog { width: min(34rem, 100%); max-height: 90vh; overflow: auto; background: var(--surface-overlay);
      border: 1px solid var(--border-strong); border-radius: var(--radius-lg); box-shadow: var(--shadow-lg); }
    .dialog__head { display: flex; justify-content: space-between; align-items: center; padding: .9rem 1.1rem; border-bottom: 1px solid var(--border); }
    .dialog__title { font-size: 1rem; }
    .dialog__close { background: none; border: 0; color: var(--text-muted); cursor: pointer; font: inherit; font-size: .8rem; }
    .dialog__close:hover { color: var(--text-primary); }
    .dialog__body { padding: 1rem 1.1rem; }
    .dialog__foot { display: flex; justify-content: flex-end; gap: .5rem; padding: .8rem 1.1rem; border-top: 1px solid var(--border); }
    .dialog__foot:empty { display: none; }
  `],
})
export class ModalComponent implements AfterViewInit, OnDestroy {
  /** Unique per dialog, so two dialogs (a confirm over a form) never share a title id. */
  readonly titleId = `modal-title-${++nextModalId}`;
  @Input({ required: true }) title!: string;
  @Output() closed = new EventEmitter<void>();
  @ViewChild('dialog', { static: true }) dialog!: ElementRef<HTMLElement>;
  private opener: HTMLElement | null = document.activeElement as HTMLElement | null;

  ngAfterViewInit(): void {
    const first = this.focusable()[0];
    (first ?? this.dialog.nativeElement).focus();
  }
  ngOnDestroy(): void { this.opener?.focus?.(); }

  @HostListener('document:keydown', ['$event'])
  onKey(e: KeyboardEvent): void {
    if (e.key === 'Escape') { e.stopPropagation(); this.closed.emit(); return; }
    if (e.key !== 'Tab') return;
    const items = this.focusable();
    if (!items.length) return;
    const first = items[0], last = items[items.length - 1];
    const active = document.activeElement;
    if (e.shiftKey && active === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus(); }
  }

  onBackdrop(e: MouseEvent): void { if (e.target === e.currentTarget) this.closed.emit(); }

  private focusable(): HTMLElement[] {
    return Array.from(this.dialog.nativeElement.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'));
  }
}
