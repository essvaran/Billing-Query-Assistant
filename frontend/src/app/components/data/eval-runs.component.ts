import { ConfirmService } from '../../shared/confirm';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CatalogService, EvalRunRow } from '../../services/catalog.service';
import { ModalComponent } from '../../shared/modal.component';
import { EmptyStateComponent, ErrorStateComponent } from '../../shared/primitives';
import { ToastService } from '../../shared/toast';
import { DATA_STYLES, apiMessage } from './data-shared';

/** Stored eval runs: what each measured, with notes. A run is created by `python -m tier1 eval`, not by hand. */
@Component({
  selector: 'app-eval-runs-admin',
  standalone: true,
  imports: [FormsModule, ModalComponent, EmptyStateComponent, ErrorStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <p class="muted">Runs are created by the evaluation (<code>python -m tier1 eval --tag NAME</code> or Insights, Evaluation). Here you can read
      them, keep notes, and delete runs you no longer need.</p>
    @if (error()) { <app-error-state message="Runs could not be loaded." retryLabel="Try again" (retry)="load()" /> }
    @else if (!rows().length) { <app-empty-state title="No runs" detail="Run an evaluation first." /> }
    @else {
      <div class="table-wrap"><table class="tbl">
        <thead><tr><th>Run</th><th>Suite</th><th>Status</th><th class="num">Passed</th><th>Notes</th><th>Updated</th><th></th></tr></thead>
        <tbody>
          @for (r of rows(); track r.tag) {
            <tr><td><code>{{ r.tag }}</code></td><td>{{ r.suite }}</td>
              <td><span class="pill" [class.ok]="r.status === 'complete'" [class.warn]="r.status === 'partial'">{{ r.status }}</span></td>
              <td class="num">{{ r.passed ?? '-' }}{{ r.n !== null ? '/' + r.n : '' }}</td>
              <td class="small">{{ r.notes }}</td><td class="small">{{ r.updated_at }}</td>
              <td class="actions"><button type="button" class="t1-btn" (click)="edit(r)">Notes</button>
                <button type="button" class="t1-btn t1-btn--danger" (click)="remove(r)">Delete</button></td></tr>
          }
        </tbody>
      </table></div>
    }
    @if (editing(); as e) {
      <app-modal [title]="'Notes for ' + e.tag" (closed)="editing.set(null)">
        <textarea class="t1-input" rows="8" style="width:100%" [(ngModel)]="e.notes" aria-label="Notes"></textarea>
        <div modal-actions>
          <button type="button" class="t1-btn" (click)="editing.set(null)">Cancel</button>
          <button type="button" class="t1-btn t1-btn--primary" (click)="save()">Save</button>
        </div>
      </app-modal>
    }
  `,
  styles: [DATA_STYLES],
})
export class EvalRunsComponent implements OnInit {
  private readonly confirm = inject(ConfirmService);
  private api = inject(CatalogService);
  private toast = inject(ToastService);
  rows = signal<EvalRunRow[]>([]);
  error = signal(false);
  editing = signal<{ tag: string; notes: string } | null>(null);

  ngOnInit(): void { this.load(); }
  load(): void {
    this.error.set(false);
    this.api.evalRuns().subscribe({ next: r => this.rows.set(r), error: () => this.error.set(true) });
  }
  edit(r: EvalRunRow): void { this.editing.set({ tag: r.tag, notes: r.notes }); }
  save(): void {
    const e = this.editing();
    if (!e) return;
    this.api.saveRunNotes(e.tag, e.notes).subscribe({ next: () => { this.editing.set(null); this.toast.success('Notes saved.'); this.load(); },
                                                     error: err => this.toast.error(apiMessage(err)) });
  }
  async remove(r: EvalRunRow): Promise<void> {
    if (!(await this.confirm.ask(`Delete run ${r.tag} and its results? The report files under docs/archive/deliverables/ stay.`, { danger: true, confirmLabel: 'Delete' }))) return;
    this.api.deleteRun(r.tag).subscribe({ next: () => { this.toast.success('Deleted.'); this.load(); }, error: err => this.toast.error(apiMessage(err)) });
  }
}
