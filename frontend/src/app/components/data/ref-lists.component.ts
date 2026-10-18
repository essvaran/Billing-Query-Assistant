import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CatalogService } from '../../services/catalog.service';
import { RefCategory, RefDataService, RefValue, refCategories } from '../../shared/ref-data';
import { ModalComponent } from '../../shared/modal.component';
import { EmptyStateComponent } from '../../shared/primitives';
import { ToastService } from '../../shared/toast';
import { DATA_STYLES, apiMessage } from './data-shared';

interface Draft { creating: boolean; code: string; label: string; description: string; sort_order: number; active: boolean;
                  meta: Record<string, string | number | boolean>; system: boolean }

/** Reference lists: every code list the app uses, with its labels and extra fields. */
@Component({
  selector: 'app-ref-lists',
  standalone: true,
  imports: [FormsModule, ModalComponent, EmptyStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="bar">
      <label class="sr-only" for="cat">List</label>
      <select id="cat" class="t1-select" [ngModel]="selected()" (ngModelChange)="selected.set($event)">
        @for (c of categories(); track c.category) { <option [value]="c.category">{{ c.label }}</option> }
      </select>
      <span class="grow"></span>
      @if (category()?.codes_editable) { <button type="button" class="t1-btn t1-btn--primary" (click)="add()">Add value</button> }
    </div>
    @if (category(); as c) {
      <p class="muted">{{ c.description }}
        @if (!c.codes_editable) { The codes are used by the application, so you can change labels and fields but not add or remove codes. }</p>
      @if (!c.values.length) { <app-empty-state title="No values" detail="Add the first value." /> }
      @else {
        <div class="table-wrap"><table class="tbl">
          <thead><tr><th>Code</th><th>Label</th>@if (hasDescriptions()) { <th>Description</th> }
            @for (f of metaFields(); track f.key) { <th>{{ f.label }}</th> }<th>Status</th><th></th></tr></thead>
          <tbody>
            @for (v of c.values; track v.code) {
              <tr [class.off]="!v.active">
                <td><code>{{ v.code }}</code></td>
                <td>{{ v.label }}</td>
                @if (hasDescriptions()) { <td class="small">{{ v.description }}</td> }
                @for (f of metaFields(); track f.key) { <td class="small">{{ show(v.meta[f.key]) }}</td> }
                <td>
                  <span class="pill" [class.ok]="v.active">{{ v.active ? 'On' : 'Off' }}</span>
                  @if (v.system) { <span class="pill accent" title="Used by the application: cannot be switched off or deleted">Built in</span> }
                </td>
                <td class="actions">
                  <button type="button" class="t1-btn" (click)="edit(v)">Edit</button>
                  @if (!v.system) {
                    <button type="button" class="t1-btn" (click)="toggle(v)">{{ v.active ? 'Switch off' : 'Switch on' }}</button>
                    @if (c.codes_editable) { <button type="button" class="t1-btn t1-btn--danger" (click)="remove(v)">Delete</button> }
                  }
                </td>
              </tr>
            }
          </tbody>
        </table></div>
      }
    }

    @if (draft(); as d) {
      <app-modal [title]="d.creating ? 'Add to ' + (category()?.label ?? '') : 'Edit ' + d.code" (closed)="draft.set(null)">
        <form class="form" (ngSubmit)="save()">
          @if (d.creating) { <label>Code <input class="t1-input" name="code" [(ngModel)]="d.code" required maxlength="60" /></label> }
          <label>Label <input class="t1-input" name="label" [(ngModel)]="d.label" required maxlength="300" /></label>
          <label>Description <textarea class="t1-input" name="desc" rows="2" [(ngModel)]="d.description" maxlength="1000"></textarea></label>
          @for (f of metaFields(); track f.key) {
            @switch (f.type) {
              @case ('bool') { <label class="check"><input type="checkbox" [name]="f.key" [(ngModel)]="d.meta[f.key]" /> {{ f.label }}</label> }
              @case ('int') { <label>{{ f.label }} <input class="t1-input" type="number" step="1" [name]="f.key" [(ngModel)]="d.meta[f.key]" /></label> }
              @case ('list') { <label>{{ f.label }} <textarea class="t1-input code" rows="5" [name]="f.key" [(ngModel)]="d.meta[f.key]"></textarea></label> }
              @default { <label>{{ f.label }} <textarea class="t1-input" rows="2" [name]="f.key" [(ngModel)]="d.meta[f.key]"></textarea></label> }
            }
          }
          <div class="two">
            <label>Order <input class="t1-input" type="number" name="order" [(ngModel)]="d.sort_order" min="0" /></label>
            @if (!d.system) { <label class="check"><input type="checkbox" name="active" [(ngModel)]="d.active" /> Active</label> }
          </div>
          @if (formError()) { <p class="err" role="alert">{{ formError() }}</p> }
        </form>
        <div modal-actions>
          <button type="button" class="t1-btn" (click)="draft.set(null)">Cancel</button>
          <button type="button" class="t1-btn t1-btn--primary" (click)="save()" [disabled]="busy()">Save</button>
        </div>
      </app-modal>
    }
  `,
  styles: [DATA_STYLES + `.check { display: flex !important; align-items: center; gap: .4rem; }`],
})
export class RefListsComponent {
  private api = inject(CatalogService);
  private refData = inject(RefDataService);
  private toast = inject(ToastService);

  categories = computed(() => Object.values(refCategories()).sort((a, b) => a.label.localeCompare(b.label)));
  selected = signal('escalation_reason');
  category = computed<RefCategory | undefined>(() => refCategories()[this.selected()]);
  metaFields = computed(() => Object.entries(this.category()?.meta_schema ?? {}).map(([key, s]) => ({ key, ...s })));
  hasDescriptions = computed(() => (this.category()?.values ?? []).some(v => v.description));
  draft = signal<Draft | null>(null);
  formError = signal('');
  busy = signal(false);

  show(v: unknown): string {
    if (Array.isArray(v)) return `${v.length} item${v.length === 1 ? '' : 's'}`;
    if (typeof v === 'boolean') return v ? 'Yes' : 'No';
    return v === undefined || v === null ? '' : String(v);
  }

  add(): void {
    const meta: Draft['meta'] = {};
    for (const f of this.metaFields()) meta[f.key] = f.type === 'bool' ? false : '';
    this.formError.set('');
    this.draft.set({ creating: true, code: '', label: '', description: '', sort_order: ((this.category()?.values.length ?? 0) + 1) * 10,
                     active: true, meta, system: false });
  }

  edit(v: RefValue): void {
    const meta: Draft['meta'] = {};
    for (const f of this.metaFields()) {
      const cur = v.meta[f.key];
      meta[f.key] = f.type === 'list' ? (Array.isArray(cur) ? cur.join('\n') : '') : f.type === 'bool' ? !!cur : (cur as string | number) ?? '';
    }
    this.formError.set('');
    this.draft.set({ creating: false, code: v.code, label: v.label, description: v.description, sort_order: v.sort_order,
                     active: v.active, meta, system: v.system });
  }

  private metaOut(d: Draft): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    for (const f of this.metaFields()) {
      const v = d.meta[f.key];
      if (f.type === 'list') out[f.key] = String(v ?? '').split('\n').map(x => x.trimEnd()).filter(Boolean);
      else if (f.type === 'int') { if (v !== '' && v !== null && v !== undefined) out[f.key] = Math.trunc(Number(v)); }
      else if (f.type === 'bool') out[f.key] = !!v;
      else if (v !== '' && v !== null && v !== undefined) out[f.key] = String(v);
    }
    return out;
  }

  save(): void {
    const d = this.draft();
    const cat = this.selected();
    if (!d || this.busy()) return;
    if (!d.label.trim() || (d.creating && !d.code.trim())) { this.formError.set('Code and label are required.'); return; }
    this.busy.set(true);
    const body = { label: d.label, description: d.description, sort_order: Number(d.sort_order), meta: this.metaOut(d),
                   ...(d.system ? {} : { active: d.active }) };
    const call = d.creating ? this.api.createValue(cat, { code: d.code.trim(), ...body }) : this.api.updateValue(cat, d.code, body);
    call.subscribe({
      next: () => { this.busy.set(false); this.draft.set(null); this.toast.success('Saved.'); this.refData.load().subscribe(); },
      error: err => { this.busy.set(false); this.formError.set(apiMessage(err)); },
    });
  }

  toggle(v: RefValue): void {
    this.api.updateValue(this.selected(), v.code, { active: !v.active }).subscribe({
      next: () => { this.toast.success(v.active ? 'Switched off.' : 'Switched on.'); this.refData.load().subscribe(); },
      error: err => this.toast.error(apiMessage(err)),
    });
  }

  remove(v: RefValue): void {
    if (!window.confirm(`Delete ${v.code}? Records that already use it keep the code but lose its label.`)) return;
    this.api.deleteValue(this.selected(), v.code).subscribe({
      next: () => { this.toast.success('Deleted.'); this.refData.load().subscribe(); },
      error: err => this.toast.error(apiMessage(err, 'Could not delete it.')),
    });
  }
}
