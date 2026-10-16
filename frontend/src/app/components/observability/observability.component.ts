import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { Subject, takeUntil } from 'rxjs';
import { ObsMeta, ObservabilityService } from '../../services/observability.service';
import { ObsTracesComponent } from './obs-traces.component';
import { ObsCostComponent } from './obs-cost.component';
import { ObsAlertsComponent } from './obs-alerts.component';
import { ObsEvalComponent } from './obs-eval.component';
import { ObsFeedbackComponent } from './obs-feedback.component';

type Tab = 'drill' | 'feedback' | 'cost' | 'alerts' | 'eval';

@Component({
  selector: 'app-observability',
  standalone: true,
  imports: [CommonModule, ObsTracesComponent, ObsCostComponent, ObsAlertsComponent, ObsEvalComponent, ObsFeedbackComponent],
  template: `
    <div class="page">
      <header class="page__head">
        <div>
          <h1>Observability</h1>
          <p class="page__sub">
            Find any bad answer, see what each request cost, get emailed about critical traces, and turn failures into tests.
          </p>
        </div>
        @if (meta) {
          <div class="chips">
            <span class="chip-tag" title="Prompt version stamped on new traces">prompt {{ meta.prompt_version }}</span>
            <span class="chip-tag" [class.chip-tag--on]="meta.alerts_enabled">alerts {{ meta.alerts_enabled ? 'on' : 'off' }}</span>
            @if (meta.langfuse_url) {
              <a class="chip-tag chip-tag--on" [href]="meta.langfuse_url" target="_blank" rel="noopener">Open Langfuse</a>
            } @else {
              <span class="chip-tag" title="Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in .env and restart the API">langfuse off</span>
            }
          </div>
        }
      </header>

      @if (meta && !meta.langfuse_configured) {
        <div class="err" role="alert">
          Langfuse is not configured, so there are no traces to show. Traces are stored only in Langfuse: set
          LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in the server .env and restart the API.
        </div>
      }

      @if (metaError) {
        <div class="err" role="alert">{{ metaError }}</div>
      }

      <div class="tabs" role="tablist" aria-label="Observability sections">
        @for (t of tabs; track t.id) {
          <button class="tab" role="tab" [class.tab--active]="tab === t.id" [attr.aria-selected]="tab === t.id"
                  (click)="select(t.id)">
            {{ t.label }}
            @if (t.id === 'feedback' && meta && meta.feedback_new_down > 0) {
              <span class="tab-badge" [attr.aria-label]="meta.feedback_new_down + ' new thumbs down'">{{ meta.feedback_new_down }}</span>
            }
          </button>
        }
      </div>

      <div class="body" role="tabpanel">
        @switch (tab) {
          @case ('drill') {
            <app-obs-traces [demoTools]="!!meta && meta.demo_tools_enabled"
                            [drillBarSeconds]="meta ? meta.drill_bar_seconds : 300"
                            [initialTraceId]="initialTraceId"
                            (openEval)="select('eval')" />
          }
          @case ('feedback') { <app-obs-feedback (openTrace)="openTrace($event)" (changed)="refreshMeta()" /> }
          @case ('cost') { <app-obs-cost /> }
          @case ('alerts') { <app-obs-alerts /> }
          @case ('eval') { <app-obs-eval /> }
        }
      </div>
    </div>
  `,
  styles: [`
    :host { display: block; }
    .page { max-width: 1240px; margin: 0 auto; padding: 1rem 0 3rem; }
    .page__head { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 0.75rem; flex-wrap: wrap; }
    h1 { margin: 0 0 0.25rem; font-size: 1.1rem; font-weight: 700; }
    .page__sub { margin: 0; color: var(--text-muted); font-size: 0.88rem; max-width: 60ch; }
    .chips { display: flex; gap: 0.4rem; }
    .chip-tag { font-size: 0.72rem; font-weight: 600; padding: 0.2rem 0.6rem; border-radius: 999px; background: rgba(108,112,134,0.25); color: var(--text-secondary); }
    .chip-tag--on { background: rgba(166,227,161,0.16); color: var(--success); text-decoration: none; }
    .tabs { display: flex; gap: 0.25rem; border-bottom: 1px solid var(--border); margin-bottom: 1rem; overflow-x: auto; }
    .tab {
      background: none; border: none; color: var(--text-muted); font: inherit; font-size: 0.88rem; font-weight: 600;
      padding: 0.6rem 1rem; cursor: pointer; border-bottom: 2px solid transparent; white-space: nowrap;
    }
    .tab:hover { color: var(--text-primary); }
    .tab:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
    .tab--active { color: var(--accent); border-bottom-color: var(--accent); }
    .tab-badge { display: inline-block; min-width: 1.2rem; margin-left: 0.35rem; padding: 0 0.35rem; border-radius: 999px; background: var(--danger); color: #11111b; font-size: 0.68rem; font-weight: 700; text-align: center; }
    .err { background: rgba(243,139,168,0.1); border: 1px solid rgba(243,139,168,0.4); color: var(--danger); padding: 0.6rem 0.85rem; border-radius: 8px; margin-bottom: 1rem; font-size: 0.85rem; }
  `],
})
export class ObservabilityComponent implements OnInit, OnDestroy {
  private api = inject(ObservabilityService);
  private destroy$ = new Subject<void>();

  readonly tabs: { id: Tab; label: string }[] = [
    { id: 'drill', label: 'Traces and support drill' },
    { id: 'feedback', label: 'User feedback' },
    { id: 'cost', label: 'Cost and 10x' },
    { id: 'alerts', label: 'Email alerts' },
    { id: 'eval', label: 'Failure to test' },
  ];

  tab: Tab = 'drill';
  meta: ObsMeta | null = null;
  metaError: string | null = null;
  /** Set when the page is opened from an alert email link (?trace=ID). */
  initialTraceId: string | null = null;
  private route = inject(ActivatedRoute);

  ngOnInit(): void {
    this.initialTraceId = this.route.snapshot.queryParamMap.get('trace');
    this.api
      .meta()
      .pipe(takeUntil(this.destroy$))
      .subscribe({ next: this.onMeta.bind(this), error: this.onMetaError.bind(this) });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  select(tab: Tab): void {
    this.tab = tab;
  }

  /** From the feedback list: jump to the trace drawer on the first tab. */
  openTrace(traceId: string): void {
    this.initialTraceId = traceId;
    this.tab = 'drill';
  }

  refreshMeta(): void {
    this.api
      .meta()
      .pipe(takeUntil(this.destroy$))
      .subscribe({ next: this.onMeta.bind(this), error: this.onMetaError.bind(this) });
  }

  private onMeta(m: ObsMeta): void {
    this.meta = m;
  }

  private onMetaError(): void {
    this.metaError = 'Could not load the observability API. Make sure the backend is running and you are signed in as an admin.';
  }
}
