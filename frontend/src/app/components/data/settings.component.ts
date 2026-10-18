import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CatalogService, SettingRow } from '../../services/catalog.service';
import { RefDataService } from '../../shared/ref-data';
import { ErrorStateComponent } from '../../shared/primitives';
import { ToastService } from '../../shared/toast';
import { DATA_STYLES, apiMessage } from './data-shared';

/** Runtime settings: budgets, limits, thresholds, models. An environment variable, when set, overrides the stored value. */
@Component({
  selector: 'app-settings-admin',
  standalone: true,
  imports: [FormsModule, ErrorStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (error()) { <app-error-state message="Settings could not be loaded." retryLabel="Try again" (retry)="load()" /> }
    @else if (!rows().length) { <div class="t1-skeleton sk"></div> }
    @else {
      <div class="bar">
        <label class="sr-only" for="q">Find a setting</label>
        <input id="q" class="t1-input" type="search" placeholder="Find a setting" [ngModel]="q()" (ngModelChange)="q.set($event)" />
      </div>
      @for (g of groups(); track g.name) {
        <section class="card">
          <h2>{{ g.name }}</h2>
          @for (s of g.rows; track s.key) {
            <div class="setting">
              <div class="setting__text">
                <label [for]="s.key"><strong>{{ s.label }}</strong></label>
                @if (s.description) { <div class="muted small">{{ s.description }}</div> }
                <div class="muted small"><code>{{ s.key }}</code>
                  @if (s.min !== null || s.max !== null) { , allowed {{ s.min ?? '' }} to {{ s.max ?? '' }} }
                  , default {{ show(s.default) }}
                  @if (s.updated_by && s.updated_by !== 'seed') { , changed by {{ s.updated_by }} {{ s.updated_at }} }</div>
                @if (s.overridden_by_env) {
                  <div class="small warn">Overridden by the environment variable <code>{{ s.env }}</code>: the app uses {{ show(s.effective) }}.</div>
                }
                @if (s.restart_required) { <div class="small muted">Takes effect after the API restarts.</div> }
              </div>
              <div class="setting__edit">
                @switch (s.type) {
                  @case ('bool') { <input [id]="s.key" type="checkbox" [(ngModel)]="edits[s.key]" /> }
                  @case ('json') { <textarea [id]="s.key" class="t1-input code" rows="6" [(ngModel)]="edits[s.key]"></textarea> }
                  @case ('str') { <input [id]="s.key" class="t1-input" [(ngModel)]="edits[s.key]" /> }
                  @default { <input [id]="s.key" class="t1-input" type="number" [step]="s.type === 'int' ? 1 : 'any'" [(ngModel)]="edits[s.key]" /> }
                }
                <div class="setting__btns">
                  <button type="button" class="t1-btn t1-btn--primary" (click)="save(s)" [disabled]="!changed(s)">Save</button>
                  <button type="button" class="t1-btn" (click)="reset(s)" [disabled]="same(s.value, s.default)">Reset to default</button>
                </div>
                @if (errors[s.key]) { <p class="err" role="alert">{{ errors[s.key] }}</p> }
              </div>
            </div>
          }
        </section>
      }
    }
  `,
  styles: [DATA_STYLES + `
    .setting { display: grid; grid-template-columns: minmax(0, 1fr) minmax(12rem, 20rem); gap: 1rem; padding: .8rem 0; border-top: 1px solid var(--border); }
    .setting:first-of-type { border-top: 0; }
    .setting__edit { display: grid; gap: .4rem; align-content: start; }
    .setting__btns { display: flex; gap: .4rem; flex-wrap: wrap; }
    .warn { color: var(--warning); }
    @media (max-width: 760px) { .setting { grid-template-columns: 1fr; } }
  `],
})
export class SettingsComponent implements OnInit {
  private api = inject(CatalogService);
  private toast = inject(ToastService);
  private refData = inject(RefDataService);
  rows = signal<SettingRow[]>([]);
  error = signal(false);
  q = signal('');
  edits: Record<string, unknown> = {};
  errors: Record<string, string> = {};

  groups = computed(() => {
    const q = this.q().trim().toLowerCase();
    const rows = this.rows().filter(s => !q || `${s.label} ${s.key} ${s.description}`.toLowerCase().includes(q));
    const names = Array.from(new Set(rows.map(r => r.group)));
    return names.map(name => ({ name, rows: rows.filter(r => r.group === name) }));
  });

  ngOnInit(): void { this.load(); }

  load(): void {
    this.error.set(false);
    this.api.settings().subscribe({
      next: rows => {
        this.rows.set(rows);
        this.edits = Object.fromEntries(rows.map(r => [r.key, r.type === 'json' ? JSON.stringify(r.value, null, 2) : r.value]));
        this.errors = {};
      },
      error: () => this.error.set(true),
    });
  }

  show(v: unknown): string { return typeof v === 'object' ? 'JSON' : String(v); }
  same(a: unknown, b: unknown): boolean { return JSON.stringify(a) === JSON.stringify(b); }

  private parsed(s: SettingRow): unknown {
    const v = this.edits[s.key];
    if (s.type === 'json') return JSON.parse(String(v));
    if (s.type === 'int' || s.type === 'float') return v === '' || v === null ? NaN : Number(v);
    return v;
  }

  changed(s: SettingRow): boolean {
    try { return !this.same(this.parsed(s), s.value); } catch { return true; }
  }

  save(s: SettingRow): void {
    let value: unknown;
    try { value = this.parsed(s); } catch { this.errors[s.key] = 'This is not valid JSON.'; return; }
    this.api.setSetting(s.key, value).subscribe({
      next: () => { this.toast.success(`${s.label} saved.`); this.load(); this.refData.load().subscribe(); },
      error: err => { this.errors = { ...this.errors, [s.key]: apiMessage(err) }; this.rows.set([...this.rows()]); },
    });
  }

  reset(s: SettingRow): void {
    this.api.resetSetting(s.key).subscribe({
      next: () => { this.toast.success(`${s.label} reset.`); this.load(); this.refData.load().subscribe(); },
      error: err => this.toast.error(apiMessage(err)),
    });
  }
}
