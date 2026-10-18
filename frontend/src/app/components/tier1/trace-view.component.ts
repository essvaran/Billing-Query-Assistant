import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { refValues } from '../../shared/ref-data';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Span, Tier1Service, TraceSummary } from '../../services/tier1.service';
import { ErrorStateComponent, KpiTileComponent } from '../../shared/primitives';
import { usd } from '../../shared/labels';

interface Row { span: Span; depth: number; left: number; width: number; offsetMs: number }

/** One trace as a waterfall: every step across the API, the agent and both MCP servers, with its cost and time. */
@Component({
  selector: 'app-trace-view',
  standalone: true,
  imports: [RouterLink, KpiTileComponent, ErrorStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="t1-page">
      <nav class="crumbs"><a routerLink="/insights">Insights</a> / <span>Trace</span></nav>
      <h1 class="t1-h1">Trace <code>{{ traceId }}</code></h1>

      @if (summary(); as s) {
        <div class="tiles">
          <app-kpi-tile label="Total time" [value]="(s.total_ms / 1000).toFixed(1) + ' s'" />
          <app-kpi-tile label="Model calls" [value]="'' + s.llm_calls" [hint]="'Waiting for the token limit: ' + s.queue_wait_s + ' s'" />
          <app-kpi-tile label="Tokens" [value]="'' + (s.input_tokens + s.output_tokens)" [hint]="s.input_tokens + ' in, ' + s.output_tokens + ' out'" />
          <app-kpi-tile label="Cost" [value]="usd(s.cost_usd)" />
          <app-kpi-tile label="Services seen" [value]="'' + s.mcp_servers_seen.length" [hint]="s.mcp_servers_seen.join(', ')" />
        </div>
        @if (s.errors.length) { <p class="err" role="alert">Steps with errors: {{ s.errors.join(', ') }}</p> }

        <div class="legend" aria-hidden="true">
          @for (k of kinds(); track k.code) { <span><i [attr.data-kind]="k.code"></i>{{ k.label }}</span> }
        </div>
        <ol class="wf" aria-label="Spans in start order">
          @for (r of rows(); track r.span.span_id) {
            <li class="wf__row">
              <div class="wf__label" [style.padding-left.rem]="r.depth * 1.1">
                <span class="name">{{ r.span.name }}</span>
                <span class="meta">{{ r.span.duration_ms.toFixed(0) }} ms
                  @if (r.span.cost_usd) { , {{ usd(r.span.cost_usd) }} }
                  @if (r.span.input_tokens) { , {{ r.span.input_tokens }}+{{ r.span.output_tokens }} tokens }
                  @if (r.span.status !== 'ok') { <strong class="bad"> error</strong> }</span>
              </div>
              <div class="wf__track"><span class="wf__bar" [attr.data-kind]="r.span.kind" [style.left.%]="r.left" [style.width.%]="r.width"
                    [attr.title]="r.span.name + ': ' + r.span.duration_ms.toFixed(0) + ' ms, starts at ' + r.offsetMs.toFixed(0) + ' ms'"></span></div>
            </li>
          }
        </ol>
      } @else if (error()) {
        <app-error-state message="This trace could not be loaded. It may not exist, or you may not have access." retryLabel="Try again" (retry)="load()" />
      } @else {
        <div class="t1-skeleton sk"></div>
      }
    </div>
  `,
  styles: [`
    .crumbs { font-size: .8rem; color: var(--text-muted); margin-bottom: .6rem; }
    code { font-size: .85em; overflow-wrap: anywhere; }
    .tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr)); gap: .75rem; margin: 1rem 0; }
    .err { color: var(--danger); font-size: .88rem; }
    .legend { display: flex; gap: 1rem; flex-wrap: wrap; font-size: .75rem; color: var(--text-muted); margin: .8rem 0; }
    .legend i, .wf__bar { background: var(--text-muted); }
    .legend i { display: inline-block; width: .7rem; height: .7rem; border-radius: 2px; margin-right: .35rem; }
    [data-kind='request'] { background: var(--text-muted); } [data-kind='llm'] { background: var(--accent); }
    [data-kind='tool'] { background: var(--yellow); } [data-kind='mcp_server'] { background: var(--success); }
    [data-kind='retrieval'] { background: var(--purple); } [data-kind='guard'] { background: var(--warning); } [data-kind='setup'] { background: var(--border-strong); }
    .wf { list-style: none; margin: 0; padding: 0; background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-lg); }
    .wf__row { display: grid; grid-template-columns: minmax(12rem, 22rem) 1fr; gap: .8rem; padding: .45rem .9rem; border-bottom: 1px solid var(--border); align-items: center; }
    .wf__row:last-child { border-bottom: 0; }
    .wf__label { display: flex; flex-direction: column; min-width: 0; } .name { font-weight: 600; font-size: .85rem; overflow-wrap: anywhere; }
    .meta { font-size: .74rem; color: var(--text-muted); } .bad { color: var(--danger); }
    .wf__track { position: relative; height: .9rem; background: var(--surface-base); border-radius: 4px; }
    .wf__bar { position: absolute; top: 0; bottom: 0; border-radius: 4px; min-width: 3px; }
    @media (max-width: 800px) { .wf__row { grid-template-columns: 1fr; } }
    .sk { height: 14rem; margin-top: 1rem; }
  `],
})
export class TraceViewComponent {
  private api = inject(Tier1Service);
  private route = inject(ActivatedRoute);
  private destroyRef = inject(DestroyRef);

  usd = usd;
  kinds() { return refValues('span_kind'); }
  traceId = '';
  summary = signal<TraceSummary | null>(null);
  spans = signal<Span[]>([]);
  error = signal(false);

  rows = computed<Row[]>(() => {
    const spans = this.spans();
    if (!spans.length) return [];
    const t0 = Math.min(...spans.map(s => Date.parse(s.started_at)));
    const end = Math.max(...spans.map(s => Date.parse(s.started_at) - t0 + s.duration_ms));
    const byId = new Map(spans.map(s => [s.span_id, s]));
    const depth = (s: Span): number => (s.parent_id && byId.has(s.parent_id) ? 1 + depth(byId.get(s.parent_id)!) : 0);
    return spans.map(span => {
      const offsetMs = Date.parse(span.started_at) - t0;
      return { span, depth: depth(span), offsetMs, left: (offsetMs / end) * 100, width: Math.max(0.4, (span.duration_ms / end) * 100) };
    });
  });

  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(p => { this.traceId = p.get('id') ?? ''; this.load(); });
  }

  load(): void {
    this.error.set(false);
    this.api.trace(this.traceId).subscribe({
      next: t => { this.summary.set(t.summary); this.spans.set(t.spans); },
      error: () => this.error.set(true),
    });
  }
}
