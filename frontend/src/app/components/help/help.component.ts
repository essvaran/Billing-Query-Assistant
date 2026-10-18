import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { NgTemplateOutlet } from '@angular/common';
import { ErrorStateComponent } from '../../shared/primitives';

export interface HelpBlock {
  type: 'heading' | 'paragraph' | 'list' | 'code' | 'table' | 'image';
  level?: number;
  text?: string;
  ordered?: boolean;
  items?: string[];
  header?: string[];
  rows?: string[][];
  alt?: string;
  src?: string;
}
export interface HelpSection { id: string; title: string; roles: string[]; blocks: HelpBlock[] }
export interface HelpResponse { title: string; role: string; sections: HelpSection[] }
export interface Inline { kind: 'text' | 'code' | 'bold'; text: string }

/** Split `code` and **bold** spans out of a line of guide text. Rendered with text bindings only: no HTML. */
export function inlineParts(text: string): Inline[] {
  const out: Inline[] = [];
  for (const part of text.split(/(`[^`]+`|\*\*[^*]+\*\*)/)) {
    if (!part) continue;
    if (part.startsWith('`') && part.endsWith('`') && part.length > 1) out.push({ kind: 'code', text: part.slice(1, -1) });
    else if (part.startsWith('**') && part.endsWith('**') && part.length > 3) out.push({ kind: 'bold', text: part.slice(2, -2) });
    else out.push({ kind: 'text', text: part });
  }
  return out;
}

/** The user guide, filtered by the server to the signed-in role. One source: FUNCTIONAL_README.md. */
@Component({
  selector: 'app-help',
  standalone: true,
  imports: [ErrorStateComponent, NgTemplateOutlet],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <!-- kept on one line: line breaks here would render as stray spaces around code and bold spans -->
    <ng-template #inl let-text="text">@for (p of parts(text); track $index) {@switch (p.kind) {@case ('code') {<code>{{ p.text }}</code>}@case ('bold') {<strong>{{ p.text }}</strong>}@default {{{ p.text }}}}}</ng-template>

    <div class="t1-page help">
      @if (error()) {
        <app-error-state message="The guide could not be loaded." retryLabel="Try again" (retry)="load()" />
      } @else if (!guide()) {
        <div class="t1-skeleton sk"></div>
      } @else {
        @let g = guide()!;
        <div class="t1-page__head">
          <div>
            <h1 class="t1-h1">{{ g.title }}</h1>
            <p class="t1-sub">{{ g.role === 'admin' ? 'You are on the support team, so you see every section.' : 'What you can do with your account, step by step.' }}</p>
          </div>
        </div>
        <div class="layout">
          <nav class="toc" aria-label="Sections">
            @for (s of g.sections; track s.id) { <a [href]="'#' + s.id" (click)="jump($event, s.id)">{{ s.title }}</a> }
          </nav>
          <article>
            @for (s of g.sections; track s.id) {
              <section class="sec" [id]="s.id">
                <h2>{{ s.title }}</h2>
                @for (b of s.blocks; track $index) {
                  @switch (b.type) {
                    @case ('heading') {
                      @if (b.level === 3) { <h3><ng-container *ngTemplateOutlet="inl; context: { text: b.text }" /></h3> }
                      @else { <h4><ng-container *ngTemplateOutlet="inl; context: { text: b.text }" /></h4> }
                    }
                    @case ('paragraph') { <p><ng-container *ngTemplateOutlet="inl; context: { text: b.text }" /></p> }
                    @case ('list') {
                      @if (b.ordered) {
                        <ol>@for (it of b.items; track $index) { <li><ng-container *ngTemplateOutlet="inl; context: { text: it }" /></li> }</ol>
                      } @else {
                        <ul>@for (it of b.items; track $index) { <li><ng-container *ngTemplateOutlet="inl; context: { text: it }" /></li> }</ul>
                      }
                    }
                    @case ('code') { <pre><code>{{ b.text }}</code></pre> }
                    @case ('table') {
                      <div class="table-wrap"><table>
                        <thead><tr>@for (h of b.header; track $index) { <th><ng-container *ngTemplateOutlet="inl; context: { text: h }" /></th> }</tr></thead>
                        <tbody>@for (r of b.rows; track $index) {
                          <tr>@for (c of r; track $index) { <td><ng-container *ngTemplateOutlet="inl; context: { text: c }" /></td> }</tr>
                        }</tbody>
                      </table></div>
                    }
                    @case ('image') { <img [src]="b.src" [alt]="b.alt" loading="lazy" /> }
                  }
                }
              </section>
            }
          </article>
        </div>
      }
    </div>
  `,
  styles: [`
    .sk { height: 20rem; }
    .layout { display: grid; grid-template-columns: 14rem minmax(0, 1fr); gap: 2rem; align-items: start; }
    .toc { position: sticky; top: 1rem; display: flex; flex-direction: column; gap: .35rem; font-size: .88rem; }
    .toc a { color: var(--text-secondary); text-decoration: none; padding: .25rem .5rem; border-radius: var(--radius-sm); }
    .toc a:hover, .toc a:focus-visible { background: var(--surface-card); color: var(--text-primary); }
    article { max-width: 48rem; line-height: 1.65; }
    .sec { scroll-margin-top: 1rem; padding-bottom: 1.5rem; margin-bottom: 1.5rem; border-bottom: 1px solid var(--border); }
    h2 { font-size: 1.3rem; margin: 0 0 .8rem; } h3 { font-size: 1.05rem; margin: 1.4rem 0 .5rem; } h4 { font-size: .95rem; margin: 1rem 0 .4rem; }
    p, li { color: var(--text-secondary); } p { margin: 0 0 .8rem; } ol, ul { padding-left: 1.3rem; } li { margin: .25rem 0; }
    code { background: var(--surface-card); border: 1px solid var(--border); border-radius: 4px; padding: 0 .3rem; font-size: .85em; }
    pre { background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-md); padding: .8rem 1rem; overflow-x: auto; }
    pre code { border: 0; padding: 0; background: none; }
    .table-wrap { overflow-x: auto; margin: .6rem 0 1rem; }
    table { border-collapse: collapse; width: 100%; font-size: .88rem; }
    th, td { text-align: left; padding: .45rem .7rem; border-bottom: 1px solid var(--border); vertical-align: top; }
    th { color: var(--text-muted); font-size: .75rem; text-transform: uppercase; letter-spacing: .04em; }
    img { max-width: 100%; border: 1px solid var(--border); border-radius: var(--radius-md); margin: .6rem 0; }
    @media (max-width: 760px) { .layout { grid-template-columns: 1fr; } .toc { position: static; flex-direction: row; flex-wrap: wrap; } }
  `],
})
export class HelpComponent implements OnInit {
  private http = inject(HttpClient);
  guide = signal<HelpResponse | null>(null);
  error = signal(false);

  ngOnInit(): void { this.load(); }

  load(): void {
    this.error.set(false);
    this.http.get<HelpResponse>('/api/help').subscribe({ next: g => this.guide.set(g), error: () => this.error.set(true) });
  }

  parts(text: string | undefined): Inline[] { return inlineParts(text ?? ''); }

  jump(e: Event, id: string): void {
    e.preventDefault();
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}
