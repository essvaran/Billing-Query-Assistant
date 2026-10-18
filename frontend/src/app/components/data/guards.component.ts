import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CatalogService, GateReport, GuardExample, GuardRules, GuardVersion } from '../../services/catalog.service';
import { refValues } from '../../shared/ref-data';
import { ModalComponent } from '../../shared/modal.component';
import { ErrorStateComponent } from '../../shared/primitives';
import { ToastService } from '../../shared/toast';
import { DATA_STYLES, apiMessage } from './data-shared';

interface EditableRules { pre: { category: string; reason: string; detail: string; patterns: string }[]; post: Record<string, string>;
                          violation_reason: Record<string, string> }

/**
 * Guard rules: the patterns that stop hostile or non-Tier-1 tickets before any model call, and check drafts after.
 * A change is a new version that must pass every stored example before it can go live; old versions can be restored.
 */
@Component({
  selector: 'app-guards-admin',
  standalone: true,
  imports: [FormsModule, ModalComponent, ErrorStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (error()) { <app-error-state message="Guard rules could not be loaded." retryLabel="Try again" (retry)="load()" /> }
    @else if (!rules()) { <div class="t1-skeleton sk"></div> }
    @else {
      @let r = rules()!;
      <section class="card">
        <h2>Rules (editing a copy of v{{ activeVersion() }})</h2>
        <p class="muted small">Before the model: the first category whose pattern matches decides the escalation. Patterns are regular
          expressions, matched case-insensitively, one per line.</p>
        @for (g of r.pre; track $index; let i = $index) {
          <div class="group">
            <div class="two">
              <label class="small">Category <input class="t1-input" [(ngModel)]="g.category" [name]="'c' + i" /></label>
              <label class="small">Escalation reason
                <select class="t1-select" [(ngModel)]="g.reason" [name]="'r' + i">
                  @for (x of reasons(); track x.code) { <option [value]="x.code">{{ x.label }}</option> }
                </select></label>
            </div>
            <label class="small">Description <input class="t1-input" [(ngModel)]="g.detail" [name]="'d' + i" /></label>
            <label class="small">Patterns <textarea class="t1-input code" rows="5" [(ngModel)]="g.patterns" [name]="'p' + i"></textarea></label>
            <button type="button" class="t1-btn t1-btn--danger" (click)="removeGroup(i)">Remove category</button>
          </div>
        }
        <button type="button" class="t1-btn" (click)="addGroup()">Add category</button>
        <h3 class="small muted" style="margin-top:1rem">After the model drafts a reply</h3>
        @for (k of postKeys(); track k) {
          <label class="small">{{ k.split('_').join(' ') }} <input class="t1-input code" [(ngModel)]="r.post[k]" [name]="'post' + k" /></label>
        }
        <div class="bar" style="margin-top:.8rem">
          <input class="t1-input grow" placeholder="Note for this version" [(ngModel)]="note" name="note" maxlength="500" />
          <button type="button" class="t1-btn" (click)="test()">Check against the examples</button>
          <button type="button" class="t1-btn t1-btn--primary" (click)="draft()">Save as draft</button>
        </div>
        @if (report(); as rep) {
          <p><span class="pill" [class.ok]="rep.passed" [class.bad]="!rep.passed">{{ rep.passed ? 'Passes every example' : 'Fails' }}</span></p>
          <ul class="checks">@for (c of failing(rep); track c.check) { <li data-ok="false">{{ c.check }} <span class="muted">({{ c.detail }})</span></li> }</ul>
        }
      </section>

      <section class="card">
        <h2>Versions</h2>
        <div class="table-wrap"><table class="tbl">
          <thead><tr><th>Version</th><th>Status</th><th>Note</th><th>Examples</th><th>Saved</th><th></th></tr></thead>
          <tbody>
            @for (v of versions(); track v.id) {
              <tr><td>v{{ v.version }}</td>
                <td><span class="pill" [class.ok]="v.status === 'active'" [class.bad]="v.status === 'rejected'" [class.warn]="v.status === 'draft'">{{ v.status }}</span></td>
                <td class="small">{{ v.note }}</td><td class="small">{{ v.test_report.passed ? 'pass' : 'fail' }}</td>
                <td class="small">{{ v.created_at }} {{ v.created_by }}</td>
                <td class="actions">
                  <button type="button" class="t1-btn" (click)="edit(v)">Open</button>
                  @if (v.status !== 'active') {
                    <button type="button" class="t1-btn t1-btn--primary" (click)="activate(v)">{{ v.status === 'retired' ? 'Restore' : 'Activate' }}</button>
                    <button type="button" class="t1-btn t1-btn--danger" (click)="removeVersion(v)">Delete</button>
                  }
                </td></tr>
            }
          </tbody>
        </table></div>
      </section>

      <section class="card">
        <div class="bar"><h2 class="grow">Examples every version must pass</h2>
          <button type="button" class="t1-btn t1-btn--primary" (click)="openExample(null)">Add example</button></div>
        <div class="table-wrap"><table class="tbl">
          <thead><tr><th>Stage</th><th>Text</th><th>Expected</th><th>Note</th><th></th></tr></thead>
          <tbody>
            @for (e of examples(); track e.id) {
              <tr><td>{{ e.stage === 'pre' ? 'Before model' : 'After model' }}</td><td>{{ e.text }}</td><td><code>{{ e.expect }}</code></td>
                <td class="small">{{ e.note }}</td>
                <td class="actions"><button type="button" class="t1-btn" (click)="openExample(e)">Edit</button>
                  <button type="button" class="t1-btn t1-btn--danger" (click)="removeExample(e)">Delete</button></td></tr>
            }
          </tbody>
        </table></div>
      </section>
    }

    @if (example(); as e) {
      <app-modal [title]="e.id ? 'Edit example' : 'Add an example'" (closed)="example.set(null)">
        <form class="form">
          <label>Stage <select class="t1-select" name="stage" [(ngModel)]="e.stage">
            <option value="pre">Before the model (pre-guard)</option><option value="post">After the model (post-guard)</option></select></label>
          <label>Text <textarea class="t1-input" rows="3" name="text" [(ngModel)]="e.text"></textarea></label>
          <label>Expected
            <select class="t1-select" name="expect" [(ngModel)]="e.expect">
              @for (x of expectOptions(e.stage ?? 'pre'); track x.value) { <option [value]="x.value">{{ x.label }}</option> }
            </select></label>
          <label>Note <input class="t1-input" name="note" [(ngModel)]="e.note" maxlength="300" /></label>
          @if (exampleError()) { <p class="err" role="alert">{{ exampleError() }}</p> }
        </form>
        <div modal-actions>
          <button type="button" class="t1-btn" (click)="example.set(null)">Cancel</button>
          <button type="button" class="t1-btn t1-btn--primary" (click)="saveExample()">Save</button>
        </div>
      </app-modal>
    }
  `,
  styles: [DATA_STYLES + `
    .group { border: 1px solid var(--border); border-radius: var(--radius-md); padding: .7rem; margin-bottom: .7rem; display: grid; gap: .5rem; }
    .two { display: grid; grid-template-columns: 1fr 1fr; gap: .6rem; }
    label.small { display: grid; gap: .2rem; }
    @media (max-width: 620px) { .two { grid-template-columns: 1fr; } }
  `],
})
export class GuardsComponent implements OnInit {
  private api = inject(CatalogService);
  private toast = inject(ToastService);
  versions = signal<GuardVersion[]>([]);
  examples = signal<GuardExample[]>([]);
  activeVersion = signal<number | null>(null);
  rules = signal<EditableRules | null>(null);
  report = signal<GateReport | null>(null);
  error = signal(false);
  example = signal<Partial<GuardExample> | null>(null);
  exampleError = signal('');
  note = '';
  postKeys = computed(() => Object.keys(this.rules()?.post ?? {}));

  ngOnInit(): void { this.load(); }

  reasons() { return refValues('escalation_reason'); }

  load(): void {
    this.error.set(false);
    this.api.guards().subscribe({
      next: g => {
        this.versions.set(g.versions);
        this.examples.set(g.examples);
        this.activeVersion.set(g.active_version);
        const active = g.versions.find(v => v.status === 'active');
        if (active && !this.rules()) this.rules.set(this.toEditable(active.rules));
      },
      error: () => this.error.set(true),
    });
  }

  private toEditable(r: GuardRules): EditableRules {
    return { pre: r.pre.map(g => ({ category: g.category, reason: g.reason, detail: g.detail ?? '', patterns: g.patterns.join('\n') })),
             post: { ...r.post }, violation_reason: { ...(r.violation_reason ?? {}) } };
  }

  private fromEditable(): GuardRules {
    const r = this.rules()!;
    return { pre: r.pre.map(g => ({ category: g.category.trim(), reason: g.reason, detail: g.detail,
                                    patterns: g.patterns.split('\n').map(p => p.trim()).filter(Boolean) })),
             post: r.post, violation_reason: r.violation_reason };
  }

  failing(r: GateReport) { return r.checks.filter(c => !c.passed); }
  addGroup(): void { this.rules.update(r => r && { ...r, pre: [...r.pre, { category: '', reason: 'other', detail: '', patterns: '' }] }); }
  removeGroup(i: number): void { this.rules.update(r => r && { ...r, pre: r.pre.filter((_, j) => j !== i) }); }
  edit(v: GuardVersion): void { this.rules.set(this.toEditable(v.rules)); this.report.set(v.test_report); }

  test(): void {
    this.api.testGuards(this.fromEditable()).subscribe({ next: r => this.report.set(r), error: err => this.toast.error(apiMessage(err)) });
  }

  draft(): void {
    this.api.draftGuards(this.fromEditable(), this.note).subscribe({
      next: r => {
        this.report.set(r.test_report);
        if (r.status === 'draft') this.toast.success(`Saved as draft v${r.version}. Activate it to make it live.`);
        else this.toast.error(`Saved as v${r.version}, but it fails the examples, so it cannot go live.`);
        this.note = '';
        this.load();
      },
      error: err => this.toast.error(apiMessage(err)),
    });
  }

  activate(v: GuardVersion): void {
    if (!window.confirm(`Make v${v.version} the live guard rules? Every ticket from now on is checked with it.`)) return;
    this.api.activateGuards(v.version).subscribe({
      next: () => { this.toast.success(`v${v.version} is live.`); this.rules.set(null); this.load(); },
      error: err => this.toast.error(apiMessage(err)),
    });
  }

  removeVersion(v: GuardVersion): void {
    if (!window.confirm(`Delete v${v.version}?`)) return;
    this.api.deleteGuards(v.version).subscribe({ next: () => { this.toast.success('Deleted.'); this.load(); }, error: err => this.toast.error(apiMessage(err)) });
  }

  expectOptions(stage: string): { value: string; label: string }[] {
    if (stage === 'post') {
      return this.postKeys().flatMap(k => [{ value: k, label: `${k} must match` }, { value: '!' + k, label: `${k} must not match` }]);
    }
    return [...(this.rules()?.pre ?? []).map(g => ({ value: g.category, label: `Caught as ${g.category}` })), { value: 'pass', label: 'Not blocked' }];
  }

  openExample(e: GuardExample | null): void {
    this.exampleError.set('');
    this.example.set(e ? { ...e } : { stage: 'pre', text: '', expect: 'pass', note: '' });
  }

  saveExample(): void {
    const e = this.example();
    if (!e) return;
    this.api.saveExample(e).subscribe({
      next: r => {
        this.example.set(null);
        if (r.live_rules_pass) this.toast.success('Example saved.');
        else this.toast.error('Example saved. The live rules do not handle it yet: edit the rules and activate a version that passes.');
        this.load();
      },
      error: err => this.exampleError.set(apiMessage(err)),
    });
  }

  removeExample(e: GuardExample): void {
    if (!window.confirm('Delete this example?')) return;
    this.api.deleteExample(e.id).subscribe({ next: () => { this.toast.success('Deleted.'); this.load(); }, error: err => this.toast.error(apiMessage(err)) });
  }
}
