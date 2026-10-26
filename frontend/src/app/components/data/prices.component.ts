import { ConfirmService } from '../../shared/confirm';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CatalogService, PriceRow } from '../../services/catalog.service';
import { ModalComponent } from '../../shared/modal.component';
import { ErrorStateComponent } from '../../shared/primitives';
import { ToastService } from '../../shared/toast';
import { DATA_STYLES, apiMessage } from './data-shared';

/** Model prices (USD per million tokens). Every cost figure in traces, evals and the 10x plan uses these. */
@Component({
  selector: 'app-prices-admin',
  standalone: true,
  imports: [FormsModule, ModalComponent, ErrorStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="bar">
      <p class="muted grow">USD per million tokens, on-demand. 'default' prices any model that is not listed.</p>
      <button type="button" class="t1-btn t1-btn--primary" (click)="open(null)">Add model</button>
    </div>
    @if (error()) { <app-error-state message="Prices could not be loaded." retryLabel="Try again" (retry)="load()" /> }
    @else {
      <div class="table-wrap"><table class="tbl">
        <thead><tr><th>Model</th><th class="num">Input</th><th class="num">Output</th><th>Source</th><th>Checked</th><th></th></tr></thead>
        <tbody>
          @for (p of rows(); track p.model) {
            <tr><td><code>{{ p.model }}</code></td><td class="num">{{ p.input_per_1m }}</td><td class="num">{{ p.output_per_1m }}</td>
              <td class="small">{{ p.source }}</td><td class="small">{{ p.checked_on }}</td>
              <td class="actions"><button type="button" class="t1-btn" (click)="open(p)">Edit</button>
                @if (p.model !== 'default') { <button type="button" class="t1-btn t1-btn--danger" (click)="remove(p)">Delete</button> }</td></tr>
          }
        </tbody>
      </table></div>
    }
    @if (form(); as f) {
      <app-modal [title]="creating() ? 'Add a model price' : 'Edit ' + f.model" (closed)="form.set(null)">
        <form class="form" (ngSubmit)="save()">
          @if (creating()) { <label>Model id <input class="t1-input" name="model" [(ngModel)]="f.model" required maxlength="120" /></label> }
          <div class="two">
            <label>Input (USD per 1M) <input class="t1-input" type="number" step="any" min="0" name="in" [(ngModel)]="f.input_per_1m" /></label>
            <label>Output (USD per 1M) <input class="t1-input" type="number" step="any" min="0" name="out" [(ngModel)]="f.output_per_1m" /></label>
          </div>
          <label>Source <input class="t1-input" name="src" [(ngModel)]="f.source" maxlength="300" /></label>
          <label>Checked on <input class="t1-input" type="date" name="chk" [(ngModel)]="f.checked_on" /></label>
          @if (formError()) { <p class="err" role="alert">{{ formError() }}</p> }
        </form>
        <div modal-actions>
          <button type="button" class="t1-btn" (click)="form.set(null)">Cancel</button>
          <button type="button" class="t1-btn t1-btn--primary" (click)="save()">Save</button>
        </div>
      </app-modal>
    }
  `,
  styles: [DATA_STYLES],
})
export class PricesComponent implements OnInit {
  private readonly confirm = inject(ConfirmService);
  private api = inject(CatalogService);
  private toast = inject(ToastService);
  rows = signal<PriceRow[]>([]);
  error = signal(false);
  form = signal<PriceRow | null>(null);
  creating = signal(false);
  formError = signal('');

  ngOnInit(): void { this.load(); }
  load(): void {
    this.error.set(false);
    this.api.prices().subscribe({ next: r => this.rows.set(r), error: () => this.error.set(true) });
  }
  open(p: PriceRow | null): void {
    this.creating.set(!p);
    this.formError.set('');
    this.form.set(p ? { ...p } : { model: '', input_per_1m: 0, output_per_1m: 0, source: '', checked_on: new Date().toISOString().slice(0, 10) });
  }
  save(): void {
    const f = this.form();
    if (!f) return;
    const body = { ...f, input_per_1m: Number(f.input_per_1m), output_per_1m: Number(f.output_per_1m) };
    (this.creating() ? this.api.createPrice(body) : this.api.updatePrice(body)).subscribe({
      next: () => { this.form.set(null); this.toast.success('Price saved.'); this.load(); },
      error: err => this.formError.set(apiMessage(err)),
    });
  }
  async remove(p: PriceRow): Promise<void> {
    if (!(await this.confirm.ask(`Delete the price for ${p.model}? Costs for it will use the default price.`, { danger: true, confirmLabel: 'Delete' }))) return;
    this.api.deletePrice(p.model).subscribe({ next: () => { this.toast.success('Deleted.'); this.load(); }, error: err => this.toast.error(apiMessage(err)) });
  }
}
