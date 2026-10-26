import { ChangeDetectionStrategy, Component, ElementRef, EventEmitter, HostListener, Input, OnChanges, OnDestroy, Output, ViewChild, inject, signal } from '@angular/core';
import { Article, Tier1Service } from '../services/tier1.service';
import { ErrorStateComponent, PolicyBadgeComponent } from './primitives';
import { refMeta } from './ref-data';
import { AuthService } from '../services/auth.service';
import { articleTitle } from './labels';

export interface PassageSplit { before: string; passage: string; after: string }

/** Locate the cited chunk inside the article body so it can be highlighted. Whitespace-insensitive. */
export function splitAtPassage(body: string, chunkText: string): PassageSplit | null {
  // a chunk is "Article: ...\nSection: ...\n\n<content>": the header lines are not in the article body
  const content = chunkText.split(/\n\n/).slice(1).join('\n\n').trim();
  const needle = content.split('\n').map(l => l.trim()).filter(Boolean)[0]?.slice(0, 60);
  if (!needle) return null;
  const start = body.indexOf(needle);
  if (start < 0) return null;
  const lastLine = content.split('\n').map(l => l.trim()).filter(Boolean).slice(-1)[0] ?? needle;
  const endAt = body.indexOf(lastLine, start);
  const end = endAt < 0 ? start + needle.length : endAt + lastLine.length;
  return { before: body.slice(0, start), passage: body.slice(start, end), after: body.slice(end) };
}

/** Right-hand drawer showing the cited article, the cited passage highlighted, and a warning for retired policy. */
@Component({
  selector: 'app-source-drawer',
  standalone: true,
  imports: [PolicyBadgeComponent, ErrorStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="scrim" (mousedown)="onScrim($event)">
      <aside #panel class="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title" tabindex="-1">
        <header class="drawer__head">
          <div>
            <h2 id="drawer-title">{{ article()?.title ?? articleTitle(slug) }}</h2>
            <div class="drawer__meta">
              @if (isAdmin) { <code>{{ slug }}</code> }
              @if (article(); as a) {
                <app-policy-badge [version]="a.policy_version" />
                <span>Updated {{ a.last_updated }}</span>
                @if (a.synthetic && isAdmin) { <span class="synthetic" title="Generated for this project, not real client content">Synthetic</span> }
              }
            </div>
          </div>
          <button type="button" class="close" (click)="closed.emit()" aria-label="Close source">Close</button>
        </header>

        @if (article(); as a) {
          @if (a.retired) {
            <div class="ribbon" role="alert">
              <strong>Retired policy.</strong> {{ retiredBanner(a.policy_version) }} It is correct
              only for legacy accounts that have not been migrated.
            </div>
          }
          <div class="body">
            @if (split(); as s) { <pre>{{ s.before }}<mark>{{ s.passage }}</mark>{{ s.after }}</pre> }
            @else { <pre>{{ a.body }}</pre> }
          </div>
        } @else if (failed()) {
          <app-error-state message="This source could not be loaded." retryLabel="Try again" (retry)="load()" />
        } @else {
          <p class="loading">Loading source</p>
        }
      </aside>
    </div>`,
  styles: [`
    .scrim { position: fixed; inset: 0; background: rgba(0,0,0,.45); z-index: 850; display: flex; justify-content: flex-end; }
    .drawer { width: min(40rem, 100%); height: 100%; overflow: auto; background: var(--surface-overlay); border-left: 1px solid var(--border-strong); box-shadow: var(--shadow-lg); }
    .drawer__head { display: flex; justify-content: space-between; gap: 1rem; padding: 1rem 1.2rem; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--surface-overlay); }
    h2 { font-size: 1.05rem; }
    .drawer__meta { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; margin-top: .35rem; font-size: .78rem; color: var(--text-muted); }
    .synthetic { padding: .1rem .4rem; border-radius: var(--radius-sm); background: rgba(203,166,247,.16); color: var(--purple); font-weight: 600; }
    .close { background: none; border: 1px solid var(--border); color: var(--text-secondary); border-radius: var(--radius-md); padding: .3rem .7rem; cursor: pointer; font: inherit; font-size: .8rem; height: fit-content; }
    .close:hover { color: var(--text-primary); border-color: var(--border-strong); }
    .ribbon { margin: .9rem 1.2rem 0; padding: .7rem .9rem; border-radius: var(--radius-md); background: rgba(250,179,135,.12); border: 1px solid rgba(250,179,135,.5); font-size: .85rem; }
    .body { padding: 1rem 1.2rem 2rem; }
    pre { white-space: pre-wrap; font-family: var(--font-sans); font-size: .9rem; line-height: 1.6; margin: 0; }
    mark { background: rgba(249,226,175,.28); color: inherit; padding: .1rem 0; border-radius: 2px; box-shadow: 0 0 0 2px rgba(249,226,175,.28); }
    .loading { padding: 1.2rem; color: var(--text-muted); }
  `],
})
export class SourceDrawerComponent implements OnChanges, OnDestroy {
  /** Customers see the article title only; the slug and the synthetic-data badge are for admins. */
  readonly isAdmin = inject(AuthService).isAdmin;
  readonly articleTitle = articleTitle;
  retiredBanner(code: string | null): string { return refMeta<string>('policy_version', code, 'retired_banner') ?? ''; }
  @Input({ required: true }) slug!: string;
  @Input() chunkText = '';
  @Output() closed = new EventEmitter<void>();
  @ViewChild('panel', { static: true }) panel!: ElementRef<HTMLElement>;

  private api = inject(Tier1Service);
  article = signal<Article | null>(null);
  failed = signal(false);
  split = signal<PassageSplit | null>(null);
  private opener = document.activeElement as HTMLElement | null;

  ngOnChanges(): void { this.load(); }
  ngOnDestroy(): void { this.opener?.focus?.(); }

  load(): void {
    this.failed.set(false);
    this.article.set(null);
    this.api.article(this.slug).subscribe({
      next: a => {
        this.article.set(a);
        this.split.set(this.chunkText ? splitAtPassage(a.body, this.chunkText) : null);
        queueMicrotask(() => this.panel.nativeElement.focus());
      },
      error: () => this.failed.set(true),
    });
  }

  @HostListener('document:keydown.escape') onEscape(): void { this.closed.emit(); }
  onScrim(e: MouseEvent): void { if (e.target === e.currentTarget) this.closed.emit(); }
}
