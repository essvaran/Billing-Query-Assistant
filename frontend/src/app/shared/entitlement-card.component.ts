import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { Entitlement } from '../services/tier1.service';
import { PolicyBadgeComponent } from './primitives';

/**
 * What THIS customer is entitled to, straight from the account system via the check_entitlement tool.
 * If the assistant answered without checking, the card says so loudly and the Approve button stays off.
 */
@Component({
  selector: 'app-entitlement-card',
  standalone: true,
  imports: [PolicyBadgeComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (entitlement) {
      <section class="card" aria-label="Customer entitlement">
        <header class="card__head">
          <h3>Entitlement</h3>
          <app-policy-badge [version]="entitlement.policy_version" />
        </header>
        <dl class="grid">
          <div><dt>Refund window</dt><dd>{{ entitlement.refund_days }} days</dd></div>
          <div><dt>Plan</dt><dd>{{ entitlement.plan }}</dd></div>
          <div><dt>Region</dt><dd>{{ entitlement.region }}</dd></div>
          <div><dt>Standard delivery</dt><dd>{{ entitlement.shipping_sla.standard_days }} business days</dd></div>
          <div><dt>Express delivery</dt><dd>{{ entitlement.shipping_sla.express_days }} business days</dd></div>
        </dl>
        @if (entitlement.refund_check; as rc) {
          <p class="check" [attr.data-ok]="rc.eligible ?? 'unknown'">
            @if (rc.error) { Order could not be checked: {{ rc.error.replace('_', ' ') }}. }
            @else {
              Order is {{ rc.days_since_purchase }} days old:
              <strong>{{ rc.eligible ? 'inside' : 'outside' }}</strong> this customer's {{ rc.refund_days }}-day window.
            }
          </p>
        }
      </section>
    } @else if (answered) {
      <section class="card card--missing" role="alert">
        <h3>Entitlement was not checked</h3>
        <p>The assistant did not look up this customer's account. Do not approve a refund or shipping answer
           until the entitlement is known.</p>
      </section>
    } @else {
      <section class="card card--idle">
        <h3>Entitlement</h3>
        @if (ran) { <p>Not checked. The assistant stopped before it looked at this customer's account.</p> }
        @else { <p>Not checked yet. It is checked when the assistant runs.</p> }
      </section>
    }`,
  styles: [`
    .card { background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: .9rem 1rem; }
    .card__head { display: flex; justify-content: space-between; align-items: center; gap: .5rem; margin-bottom: .6rem; }
    h3 { font-size: .8rem; text-transform: uppercase; letter-spacing: .05em; color: var(--text-muted); }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: .5rem .9rem; margin: 0; }
    dt { font-size: .7rem; color: var(--text-muted); } dd { margin: .1rem 0 0; font-weight: 600; font-size: .88rem; }
    .check { margin-top: .75rem; padding-top: .65rem; border-top: 1px solid var(--border); font-size: .85rem; color: var(--text-secondary); }
    .check[data-ok='true'] strong { color: var(--success); } .check[data-ok='false'] strong { color: var(--danger); }
    .card--missing { border-color: rgba(243,139,168,.55); background: rgba(243,139,168,.08); }
    .card--missing h3 { color: var(--danger); } .card--missing p, .card--idle p { font-size: .85rem; margin-top: .3rem; color: var(--text-secondary); }
  `],
})
export class EntitlementCardComponent {
  @Input() entitlement: Entitlement | null = null;
  /** True when the assistant produced an answer (so a missing entitlement is a problem, not just "not run yet"). */
  @Input() answered = false;
  /** True once the assistant has run at all (so "not checked" means it stopped early, not that it has not started). */
  @Input() ran = false;
}
