import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CatalogService, ChangeRow } from '../../services/catalog.service';
import { EmptyStateComponent, ErrorStateComponent } from '../../shared/primitives';
import { DATA_STYLES } from './data-shared';

/** Who changed which list, setting, price, prompt, rule or eval case, and when. */
@Component({
  selector: 'app-changes-admin',
  standalone: true,
  imports: [FormsModule, EmptyStateComponent, ErrorStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="bar">
      <label class="sr-only" for="ent">Kind of change</label>
      <select id="ent" class="t1-select" [ngModel]="entity()" (ngModelChange)="entity.set($event); load()">
        <option value="">Everything</option>
        <option value="ref:">Reference lists</option><option value="setting">Settings</option><option value="model_price">Model prices</option>
        <option value="prompt">Prompts</option><option value="guard">Guard rules and examples</option><option value="eval">Eval cases, runs, labels</option><option value="tier1:">Tier-1 customers, orders, tickets</option>
      </select>
      <button type="button" class="t1-btn" (click)="load()">Refresh</button>
    </div>
    @if (error()) { <app-error-state message="The change log could not be loaded." retryLabel="Try again" (retry)="load()" /> }
    @else if (!rows().length) { <app-empty-state title="No changes yet" detail="Edits made on this page appear here." /> }
    @else {
      <div class="table-wrap"><table class="tbl">
        <thead><tr><th>When</th><th>Who</th><th>What</th><th>Action</th><th>Details</th></tr></thead>
        <tbody>
          @for (c of rows(); track c.id) {
            <tr><td class="small">{{ c.at }}</td><td class="small">{{ c.actor }}</td><td><code>{{ c.entity }}</code> {{ c.entity_id }}</td>
              <td>{{ c.action }}</td>
              <td class="small">@if (c.before) { <div><span class="muted">before</span> {{ short(c.before) }}</div> }
                @if (c.after) { <div><span class="muted">after</span> {{ short(c.after) }}</div> }</td></tr>
          }
        </tbody>
      </table></div>
    }
  `,
  styles: [DATA_STYLES],
})
export class ChangesComponent implements OnInit {
  private api = inject(CatalogService);
  rows = signal<ChangeRow[]>([]);
  error = signal(false);
  entity = signal('');
  ngOnInit(): void { this.load(); }
  load(): void {
    this.error.set(false);
    this.api.changes(this.entity()).subscribe({ next: r => this.rows.set(r), error: () => this.error.set(true) });
  }
  short(json: string): string { return json.length > 160 ? json.slice(0, 160) + '...' : json; }
}
