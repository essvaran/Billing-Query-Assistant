import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { LabelRepliesComponent } from './label-replies.component';

const item = (id: string, label: string | null = null) => ({
  case_id: id, subject: 'Refund', body: 'Can I get my money back?', reply: `Reply ${id} [1]`,
  account_facts: { entitlement: null, order: { order_id: 'O2077', status: 'delivered' } },
  sources: [{ chunk_id: 'K1', slug: 'refund-policy-30d', policy_version: 'refund-30d', text: 'x' }], label,
});

describe('LabelRepliesComponent', () => {
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LabelRepliesComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
  });

  function open(labeler = 'Sam Lee', items = [item('C01'), item('C02')]) {
    const fixture = TestBed.createComponent(LabelRepliesComponent);
    fixture.detectChanges();
    http.expectOne('/api/tier1/labels/runs').flush([{ tag: 'fix1', answers: items.length }]);
    http.expectOne(r => r.url === '/api/tier1/labels/queue').flush({
      tag: 'fix1', labeler, queue_experience: '2 years', min_labels: 20, target: 0.85, items });
    fixture.detectChanges();
    return fixture;
  }

  it('asks who is labelling before showing any reply', () => {
    const el = open('').nativeElement as HTMLElement;
    expect(el.textContent).toContain('Before you start');
    expect(el.textContent).not.toContain('Reply C01');
  });

  it('shows the reply and sources but never a judge verdict', () => {
    const el = open().nativeElement as HTMLElement;
    expect(el.textContent).toContain('Reply C01 [1]');
    expect(el.textContent).toContain('refund-policy-30d');
    expect(el.textContent).toContain('order id: O2077');
    expect(el.textContent?.toLowerCase()).not.toContain('verdict');
  });

  it('labels with the G key and moves to the next reply', () => {
    const fixture = open();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'g' }));
    const req = http.expectOne('/api/tier1/labels/C01');
    expect(req.request.body).toEqual({ tag: 'fix1', label: 'GOOD' });
    req.flush({ case_id: 'C01', label: 'GOOD' });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Reply C02 [1]');
    expect(fixture.componentInstance.labelled()).toBe(1);
  });

  it('keeps agreement locked below the minimum', () => {
    const el = open().nativeElement as HTMLElement;
    const btn = Array.from(el.querySelectorAll('button')).find(b => b.textContent?.includes('Check agreement'));
    expect(btn?.disabled).toBeTrue();
  });

  afterEach(() => http.verify());
});
