import { TestBed } from '@angular/core/testing';
import { Entitlement, Step, TicketAnswer } from '../services/tier1.service';
import { DecisionBannerComponent, KpiTileComponent, PolicyBadgeComponent } from './primitives';
import { EntitlementCardComponent } from './entitlement-card.component';
import { StepTimelineComponent } from './step-timeline.component';
import { splitAtPassage } from './source-drawer.component';
import { numberedSources } from '../components/tier1/ticket-workspace.component';
import { pct, usd, policyLabel, reasonLabel } from './labels';
import { loadSeedRefData } from '../../testing/seed-ref-data';

beforeAll(() => loadSeedRefData());

const ENT: Entitlement = {
  customer_id: 'C1', plan: 'premium', region: 'EU', policy_version: 'refund-14d', refund_days: 14,
  shipping_sla: { standard_days: 6, express_days: 3 },
  refund_check: { order_id: 'O1', days_since_purchase: 20, refund_days: 14, eligible: false },
};

function render<T>(type: new () => T, inputs: Record<string, unknown>): HTMLElement {
  const fixture = TestBed.createComponent(type as never);
  for (const [k, v] of Object.entries(inputs)) fixture.componentRef.setInput(k, v);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('labels', () => {
  it('never turns an unmeasured number into zero', () => {
    expect(pct(null)).toBe('Not measured');
    expect(pct(0)).toBe('0%');
    expect(usd(undefined)).toBe('Not measured');
  });
  it('names both policy versions and falls back to a person for unknown reasons', () => {
    expect(policyLabel('refund-30d')).toBe('30-day policy');
    expect(policyLabel('refund-14d')).toBe('14-day legacy policy');
    expect(reasonLabel('something_new')).toContain('person');
  });
});

describe('EntitlementCardComponent', () => {
  beforeEach(() => TestBed.configureTestingModule({ imports: [EntitlementCardComponent] }));

  it('shows the customer\'s policy, window and whether the order is inside it', () => {
    const el = render(EntitlementCardComponent, { entitlement: ENT, answered: true });
    expect(el.textContent).toContain('14-day legacy policy');
    expect(el.textContent).toContain('14 days');
    expect(el.textContent).toContain('outside');
  });

  it('is loud when the assistant answered without checking', () => {
    const el = render(EntitlementCardComponent, { entitlement: null, answered: true });
    expect(el.querySelector('[role="alert"]')).not.toBeNull();
    expect(el.textContent).toContain('was not checked');
  });

  it('says "not checked yet" before the assistant has run, and "stopped early" after', () => {
    expect(render(EntitlementCardComponent, { entitlement: null }).textContent).toContain('Not checked yet');
    expect(render(EntitlementCardComponent, { entitlement: null, ran: true }).textContent).toContain('stopped before');
  });
});

describe('PolicyBadgeComponent', () => {
  beforeEach(() => TestBed.configureTestingModule({ imports: [PolicyBadgeComponent] }));

  it('warns on the retired policy in its tooltip and text', () => {
    const el = render(PolicyBadgeComponent, { version: 'refund-14d' });
    expect(el.textContent).toContain('legacy');
    expect(el.querySelector('span')!.getAttribute('title')).toContain('Retired');
  });
});

describe('KpiTileComponent', () => {
  beforeEach(() => TestBed.configureTestingModule({ imports: [KpiTileComponent] }));

  it('renders an unmeasured value in the quiet style', () => {
    const el = render(KpiTileComponent, { label: 'Judge agreement', value: 'Not measured' });
    expect(el.querySelector('.tile--unmeasured')).not.toBeNull();
  });
});

describe('DecisionBannerComponent', () => {
  beforeEach(() => TestBed.configureTestingModule({ imports: [DecisionBannerComponent] }));

  const base = { reply: '', customer_reply: '', trace_id: 't', citations: [], entitlement: null, sources: [], tools_called: [],
                 violations: [], handoff_id: '', laps: 0, total_tokens: 0, cost_usd: 0, latency_ms: 0, budget_hit: '', error: '', draft: '' };

  it('says why it escalated, in plain words', () => {
    const result = { ...base, decision: 'ESCALATE', reason: 'legal_or_safety', handoff_id: 'H-1' } as TicketAnswer;
    const el = render(DecisionBannerComponent, { result });
    expect(el.textContent).toContain('Escalation recommended');
    expect(el.textContent).toContain('legal action');
    expect(el.textContent).toContain('handoff');
  });

  it('asks for a review, not a send, when it answered', () => {
    const el = render(DecisionBannerComponent, { result: { ...base, decision: 'ANSWER', reason: '' } as TicketAnswer });
    expect(el.textContent).toContain('Draft ready for your review');
  });
});

describe('StepTimelineComponent', () => {
  beforeEach(() => TestBed.configureTestingModule({ imports: [StepTimelineComponent] }));

  const steps: Step[] = [
    { type: 'guard', stage: 'pre', blocked: false },
    { type: 'tool_call', tool: 'check_entitlement', args: {} },
    { type: 'tool_result', tool: 'check_entitlement', result: { policy_version: 'refund-14d', refund_days: 14 } },
    { type: 'tool_call', tool: 'search_help_centre', args: {} },
  ];

  it('merges a call and its result into one readable row and keeps unfinished calls running', () => {
    const el = render(StepTimelineComponent, { steps, running: true });
    const rows = Array.from(el.querySelectorAll('.step'));
    expect(rows.some(r => r.textContent!.includes('Checked what this customer is entitled to') && r.getAttribute('data-state') === 'ok')).toBeTrue();
    expect(rows.some(r => r.textContent!.includes('Searching the help centre') && r.getAttribute('data-state') === 'running')).toBeTrue();
    expect(el.textContent).toContain('refund-14d policy, 14-day window');
  });

  it('shows a blocked safety check as blocked, not as an error', () => {
    const el = render(StepTimelineComponent, { steps: [{ type: 'guard', stage: 'pre', blocked: true, category: 'legal_or_safety' }] });
    expect(el.querySelector('[data-state="blocked"]')).not.toBeNull();
  });

  it('never shows raw ids from tool arguments', () => {
    const el = render(StepTimelineComponent, { steps: [{ type: 'tool_call', tool: 'lookup_order', args: { order_id: 'O2000' } }] });
    expect(el.textContent).not.toContain('O2000');
  });
});

describe('splitAtPassage', () => {
  const body = '# Policy\n\n## Refund window\n\nYou may request a refund within 14 days.\nThe window starts on the purchase date.\n\n## Eligibility\n\nOther text.';

  it('finds the cited passage so it can be highlighted', () => {
    const chunk = 'Article: Policy\nSection: Refund window\n\nYou may request a refund within 14 days.\nThe window starts on the purchase date.';
    const s = splitAtPassage(body, chunk)!;
    expect(s.passage).toContain('within 14 days');
    expect(s.passage).toContain('purchase date');
    expect(s.before + s.passage + s.after).toBe(body);
    expect(s.after).toContain('Eligibility');
  });

  it('returns null rather than guessing when the passage is not in the article', () => {
    expect(splitAtPassage(body, 'Article: X\nSection: Y\n\nnot present anywhere')).toBeNull();
    expect(splitAtPassage(body, '')).toBeNull();
  });
});

describe('numberedSources', () => {
  const cites = [{ chunk_id: 'a', slug: 'refund-policy-30d', policy_version: 'refund-30d' as const, doc_type: 'policy', display: '[x]' }];

  it('reads the numbered footer of the customer text and links each line to its citation', () => {
    const text = 'Within the window [1].\n\nSources:\n[1] refund-policy-30d (30-day refund policy)\n[2] shipping-sla-matrix';
    const out = numberedSources(text, cites);
    expect(out.map(o => o.n)).toEqual([1, 2]);
    expect(out[0].citation?.policy_version).toBe('refund-30d');
    expect(out[1].citation).toBeUndefined();
  });

  it('returns nothing when there is no sources footer', () => {
    expect(numberedSources('Please reset your password.', [])).toEqual([]);
  });
});
