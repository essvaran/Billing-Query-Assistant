import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CatalogService, GateReport, PromptRow, PromptVersion } from '../../services/catalog.service';
import { ErrorStateComponent } from '../../shared/primitives';
import { ToastService } from '../../shared/toast';
import { DATA_STYLES, apiMessage } from './data-shared';

/**
 * Prompts with version history. An edit is saved as a draft and checked (placeholders, required phrases the
 * application relies on, length, plain ASCII); only a draft that passes can be activated. Any older version can be
 * restored the same way.
 */
@Component({
  selector: 'app-prompts-admin',
  standalone: true,
  imports: [FormsModule, ErrorStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (error()) { <app-error-state message="Prompts could not be loaded." retryLabel="Try again" (retry)="load()" /> }
    @else if (!prompts().length) { <div class="t1-skeleton sk"></div> }
    @else {
      <div class="bar">
        <label class="sr-only" for="p">Prompt</label>
        <select id="p" class="t1-select" [ngModel]="name()" (ngModelChange)="pick($event)">
          @for (p of prompts(); track p.name) { <option [value]="p.name">{{ p.label }} (v{{ p.active_version }})</option> }
        </select>
      </div>
      @if (current(); as p) {
        <section class="card">
          <h2>{{ p.label }}</h2>
          <p class="muted small">{{ p.description }} Used by <code>{{ p.used_by }}</code>.</p>
          @if (p.placeholders.length) { <p class="small">Placeholders it must keep: @for (ph of p.placeholders; track ph) { <code>{{ '{{' + ph + '}}' }}</code> } </p> }
          @if (p.required_phrases.length) { <p class="small">Phrases the application relies on: @for (r of p.required_phrases; track r) { <code>{{ r }}</code> } </p> }
          <label class="sr-only" for="body">Prompt text</label>
          <textarea id="body" class="t1-input code" rows="18" [ngModel]="body()" (ngModelChange)="body.set($event); report.set(null)"></textarea>
          <div class="bar" style="margin-top:.6rem">
            <input class="t1-input grow" placeholder="Note for this version (what changed and why)" [ngModel]="note()" (ngModelChange)="note.set($event)" maxlength="500" />
            <button type="button" class="t1-btn" (click)="test()">Check</button>
            <button type="button" class="t1-btn t1-btn--primary" (click)="draft()" [disabled]="body() === activeBody()">Save as draft</button>
          </div>
          @if (report(); as r) {
            <p><span class="pill" [class.ok]="r.passed" [class.bad]="!r.passed">{{ r.passed ? 'Passes the checks' : 'Does not pass' }}</span></p>
            <ul class="checks">@for (c of r.checks; track c.check) { <li [attr.data-ok]="c.passed">{{ c.check }} @if (c.detail) { <span class="muted">({{ c.detail }})</span> }</li> }</ul>
          }
        </section>
        <section class="card">
          <h2>Versions</h2>
          <div class="table-wrap"><table class="tbl">
            <thead><tr><th>Version</th><th>Status</th><th>Note</th><th>Checks</th><th>Saved</th><th></th></tr></thead>
            <tbody>
              @for (v of p.versions; track v.id) {
                <tr>
                  <td>v{{ v.version }}</td>
                  <td><span class="pill" [class.ok]="v.status === 'active'" [class.bad]="v.status === 'rejected'" [class.warn]="v.status === 'draft'">{{ v.status }}</span></td>
                  <td class="small">{{ v.note }}</td>
                  <td class="small">{{ v.test_report.passed ? 'pass' : 'fail' }}</td>
                  <td class="small">{{ v.created_at }} {{ v.created_by }}</td>
                  <td class="actions">
                    <button type="button" class="t1-btn" (click)="load_into_editor(v)">Open</button>
                    @if (v.status !== 'active') {
                      <button type="button" class="t1-btn t1-btn--primary" (click)="activate(v)" [disabled]="!v.test_report.passed">
                        {{ v.status === 'retired' ? 'Restore' : 'Activate' }}</button>
                      <button type="button" class="t1-btn t1-btn--danger" (click)="remove(v)">Delete</button>
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table></div>
        </section>
      }
    }
  `,
  styles: [DATA_STYLES],
})
export class PromptsComponent implements OnInit {
  private api = inject(CatalogService);
  private toast = inject(ToastService);
  prompts = signal<PromptRow[]>([]);
  error = signal(false);
  name = signal('');
  body = signal('');
  note = signal('');
  report = signal<GateReport | null>(null);
  current = computed(() => this.prompts().find(p => p.name === this.name()));
  activeBody = computed(() => this.current()?.versions.find(v => v.status === 'active')?.body ?? '');

  ngOnInit(): void { this.load(); }

  load(keep = false): void {
    this.error.set(false);
    this.api.prompts().subscribe({
      next: list => {
        this.prompts.set(list);
        if (!keep || !this.name()) this.pick(this.name() || list[0]?.name || '');
      },
      error: () => this.error.set(true),
    });
  }

  pick(name: string): void {
    this.name.set(name);
    this.body.set(this.activeBody());
    this.note.set('');
    this.report.set(null);
  }

  load_into_editor(v: PromptVersion): void { this.body.set(v.body); this.report.set(v.test_report); }

  test(): void {
    this.api.testPrompt(this.name(), this.body()).subscribe({ next: r => this.report.set(r), error: err => this.toast.error(apiMessage(err)) });
  }

  draft(): void {
    this.api.draftPrompt(this.name(), this.body(), this.note()).subscribe({
      next: r => {
        this.report.set(r.test_report);
        this.toast[r.status === 'draft' ? 'success' : 'error'](r.status === 'draft'
          ? `Saved as draft v${r.version}. Activate it to make it live.` : `Saved as v${r.version}, but it does not pass the checks.`);
        this.load(true);
      },
      error: err => this.toast.error(apiMessage(err)),
    });
  }

  activate(v: PromptVersion): void {
    if (!window.confirm(`Make v${v.version} the live version of this prompt?`)) return;
    this.api.activatePrompt(this.name(), v.version).subscribe({
      next: () => { this.toast.success(`v${v.version} is live.`); this.load(true); setTimeout(() => this.body.set(this.activeBody()), 300); },
      error: err => this.toast.error(apiMessage(err)),
    });
  }

  remove(v: PromptVersion): void {
    if (!window.confirm(`Delete v${v.version}?`)) return;
    this.api.deletePromptVersion(this.name(), v.version).subscribe({
      next: () => { this.toast.success('Deleted.'); this.load(true); },
      error: err => this.toast.error(apiMessage(err)),
    });
  }
}
