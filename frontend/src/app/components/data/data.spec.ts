import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { loadSeedRefData } from '../../../testing/seed-ref-data';
import { refLabel, refValues } from '../../shared/ref-data';
import { Tier1DataComponent } from './tier1-data.component';
import { EvalCasesComponent } from './eval-cases.component';

describe('reference store', () => {
  beforeAll(() => loadSeedRefData());

  it('labels codes from the stored lists and falls back to the code for unknown ones', () => {
    expect(refValues('policy_version').length).toBeGreaterThan(1);
    expect(refLabel('policy_version', 'refund-30d')).not.toBe('refund-30d');
    expect(refLabel('policy_version', 'no-such-code')).toBe('no-such-code');
  });
});

describe('Tier1DataComponent', () => {
  let http: HttpTestingController;
  beforeAll(() => loadSeedRefData());
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Tier1DataComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  function open(kind: 'customers' | 'orders' | 'tickets', rows: Record<string, unknown>[]) {
    const fixture = TestBed.createComponent(Tier1DataComponent);
    fixture.componentRef.setInput('kind', kind);
    fixture.detectChanges();
    http.expectOne(r => r.url === `/api/admin/tier1/${kind}`).flush(rows);
    fixture.detectChanges();
    return fixture;
  }

  it('shows stored codes with their list labels', () => {
    const el = open('customers', [{ customer_id: 'C001', name: 'A', region: 'EU', plan: 'pro', policy_version: 'refund-30d',
                                    refund_days: 30, orders: 2 }]).nativeElement as HTMLElement;
    expect(el.textContent).toContain('C001');
    expect(el.textContent).toContain(refLabel('policy_version', 'refund-30d'));
  });

  it('offers the stored list values in the form and sends only filled fields on create', () => {
    const fixture = open('orders', []);
    const c = fixture.componentInstance;
    c.open(null);
    fixture.detectChanges();
    const options = Array.from((fixture.nativeElement as HTMLElement).querySelectorAll('select option')).map(o => o.textContent?.trim());
    expect(options).toEqual(refValues('tier1_order_status').map(v => v.label));
    c.form.set({ ...c.form()!, order_id: 'O9001', customer_id: 'C001', purchase_date: '2026-10-01', amount: '12.5' });
    c.save();
    const req = http.expectOne('/api/admin/tier1/orders');
    expect(req.request.method).toBe('POST');
    expect(req.request.body.amount).toBe(12.5);
    expect(req.request.body.status).toBe(refValues('tier1_order_status')[0].code);
    req.flush({});
    http.expectOne(r => r.url === '/api/admin/tier1/orders').flush([]);
  });

  it('keeps the form open and shows the server reason when a save is refused', () => {
    const fixture = open('tickets', []);
    const c = fixture.componentInstance;
    c.open(null);
    c.save();
    http.expectOne('/api/admin/tier1/tickets').flush({ detail: 'Order O1 belongs to another customer.' }, { status: 422, statusText: 'x' });
    expect(c.form()).not.toBeNull();
    expect(c.formError()).toContain('another customer');
  });
});

describe('EvalCasesComponent', () => {
  let http: HttpTestingController;
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [EvalCasesComponent],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
  });

  it('refuses to send case fields that are not JSON', () => {
    const fixture = TestBed.createComponent(EvalCasesComponent);
    fixture.detectChanges();
    http.expectOne(r => r.url === '/api/admin/eval/cases').flush([]);
    const c = fixture.componentInstance;
    c.open(null);
    c.form.set({ ...c.form()!, json: '{ not json' });
    c.save();
    http.expectNone('/api/admin/eval/cases');
    expect(c.formError()).toContain('not valid JSON');
  });
});
