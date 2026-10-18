import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { RefListsComponent } from './ref-lists.component';
import { SettingsComponent } from './settings.component';
import { PricesComponent } from './prices.component';
import { PromptsComponent } from './prompts.component';
import { GuardsComponent } from './guards.component';
import { EvalCasesComponent } from './eval-cases.component';
import { EvalRunsComponent } from './eval-runs.component';
import { Tier1DataComponent } from './tier1-data.component';
import { ChangesComponent } from './changes.component';

type Section = 'lists' | 'settings' | 'prices' | 'prompts' | 'guards' | 'cases' | 'runs' | 'customers' | 'orders' | 'tickets' | 'changes';

/** Admin: every list, setting, price, prompt, rule and data set the app runs on, with create, edit and delete. */
@Component({
  selector: 'app-data',
  standalone: true,
  imports: [RefListsComponent, SettingsComponent, PricesComponent, PromptsComponent, GuardsComponent, EvalCasesComponent,
            EvalRunsComponent, Tier1DataComponent, ChangesComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="t1-page">
      <div class="t1-page__head">
        <div>
          <h1 class="t1-h1">Data</h1>
          <p class="t1-sub">Everything the assistant and the app run on. Edits take effect within seconds; every change is logged.</p>
        </div>
      </div>
      <div class="layout">
        <nav class="side" aria-label="Data sections">
          @for (g of groups; track g.title) {
            <div class="side__group">{{ g.title }}</div>
            @for (s of g.items; track s.key) {
              <button type="button" [class.active]="section() === s.key" [attr.aria-current]="section() === s.key ? 'page' : null"
                      (click)="go(s.key)">{{ s.label }}</button>
            }
          }
        </nav>
        <section class="main">
          @switch (section()) {
            @case ('lists') { <app-ref-lists /> }
            @case ('settings') { <app-settings-admin /> }
            @case ('prices') { <app-prices-admin /> }
            @case ('prompts') { <app-prompts-admin /> }
            @case ('guards') { <app-guards-admin /> }
            @case ('cases') { <app-eval-cases-admin /> }
            @case ('runs') { <app-eval-runs-admin /> }
            @case ('customers') { <app-tier1-data kind="customers" /> }
            @case ('orders') { <app-tier1-data kind="orders" /> }
            @case ('tickets') { <app-tier1-data kind="tickets" /> }
            @case ('changes') { <app-changes-admin /> }
          }
        </section>
      </div>
    </div>
  `,
  styles: [`
    .layout { display: grid; grid-template-columns: 13rem minmax(0, 1fr); gap: 1.5rem; align-items: start; }
    .side { display: flex; flex-direction: column; gap: .15rem; position: sticky; top: 1rem; }
    .side__group { font-size: .7rem; text-transform: uppercase; letter-spacing: .05em; color: var(--text-muted); margin: .8rem 0 .25rem .5rem; }
    .side button { text-align: left; background: none; border: 0; color: var(--text-secondary); padding: .4rem .6rem; border-radius: var(--radius-md); font: inherit; font-size: .88rem; cursor: pointer; }
    .side button:hover { background: var(--surface-card); color: var(--text-primary); }
    .side button.active { background: rgba(137,180,250,.14); color: var(--accent); font-weight: 600; }
    @media (max-width: 760px) {
      .layout { grid-template-columns: 1fr; }
      .side { position: static; flex-direction: row; flex-wrap: wrap; }
      .side__group { width: 100%; margin: .4rem 0 0; }
    }
  `],
})
export class DataComponent {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  readonly groups: { title: string; items: { key: Section; label: string }[] }[] = [
    { title: 'Configuration', items: [
      { key: 'lists', label: 'Reference lists' }, { key: 'settings', label: 'Settings' }, { key: 'prices', label: 'Model prices' }] },
    { title: 'Assistant', items: [{ key: 'prompts', label: 'Prompts' }, { key: 'guards', label: 'Guard rules' }] },
    { title: 'Evaluation', items: [{ key: 'cases', label: 'Eval cases' }, { key: 'runs', label: 'Eval runs' }] },
    { title: 'Tier-1 data', items: [{ key: 'customers', label: 'Customers' }, { key: 'orders', label: 'Orders' }, { key: 'tickets', label: 'Tickets' }] },
    { title: 'History', items: [{ key: 'changes', label: 'Change log' }] },
  ];
  section = signal<Section>((this.route.snapshot.queryParamMap.get('s') as Section) || 'lists');

  go(s: Section): void {
    this.section.set(s);
    this.router.navigate([], { queryParams: { s }, replaceUrl: true });
  }
}
