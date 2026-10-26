import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ChatComponent } from './chat.component';
import { loadSeedRefData } from '../../../testing/seed-ref-data';

beforeAll(() => loadSeedRefData());

const OWN = { customer_id: 'C1000', region: 'US', plan: 'standard', policy_version: 'refund-30d' };
const ANSWER = { answer: 'ERR-4032 means a required field is missing [1].', chunks: [], retrieval_ms: 1, generation_ms: 1,
                 total_ms: 2, citations_valid: true, retriever: 'hybrid-bm25-rrf', trace_id: null };

async function setup(me: object): Promise<{ fixture: ComponentFixture<ChatComponent>; http: HttpTestingController }> {
  await TestBed.configureTestingModule({
    imports: [ChatComponent], providers: [provideHttpClient(), provideHttpClientTesting()],
  }).compileComponents();
  const http = TestBed.inject(HttpTestingController);
  const fixture = TestBed.createComponent(ChatComponent);
  fixture.detectChanges();
  http.expectOne('/api/feedback/reasons').flush([]);
  http.expectOne('/api/tier1/me/customer').flush(me);
  fixture.detectChanges();
  return { fixture, http };
}

function ask(fixture: ComponentFixture<ChatComponent>, text: string): void {
  fixture.componentInstance.inputText = text;
  fixture.componentInstance.sendMessage();
  fixture.detectChanges();
}

describe('ChatComponent routing', () => {
  it('shows customers no mode selector and lets the front desk pick Docs', async () => {
    const { fixture, http } = await setup({ customer: OWN, can_choose: false });
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('select[aria-label="Mode (admin)"]')).toBeNull();

    ask(fixture, 'What does ERR-4032 mean?');
    const route = http.expectOne('/api/chat/route');
    expect(route.request.body).toEqual({ text: 'What does ERR-4032 mean?', customer_id: undefined });
    route.flush({ route: 'docs', source: 'code', reason: 'ERR-4032', needs_account: false });
    http.expectOne('/api/ask').flush(ANSWER);
    fixture.detectChanges();

    expect(el.querySelector('.routed-from')?.textContent).toContain('help articles');
    expect(el.querySelector('.routed-note')).toBeNull();
    http.verify();
  });

  it('sends account questions to the assistant', async () => {
    const { fixture, http } = await setup({ customer: OWN, can_choose: false });
    ask(fixture, 'Where is my order O2017?');
    http.expectOne('/api/chat/route').flush({ route: 'agent', source: 'rule', reason: 'order id', needs_account: false });
    const answer = http.expectOne('/api/tier1/answer');
    expect(answer.request.body.text).toBe('Where is my order O2017?');
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('.agent-bubble .routed-from')?.textContent)
      .toContain('your account');
  });

  it('explains why an account question was answered from the help articles', async () => {
    const { fixture, http } = await setup({ customer: null, can_choose: false });
    ask(fixture, 'Where is my order O2017?');
    http.expectOne('/api/chat/route').flush({ route: 'docs', source: 'rule', reason: 'order id', needs_account: true });
    http.expectOne('/api/ask').flush(ANSWER);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('.routed-note')?.textContent).toContain('No customer account');
    http.verify();
  });

  it('falls back to the help articles when routing fails', async () => {
    const { fixture, http } = await setup({ customer: OWN, can_choose: false });
    ask(fixture, 'Hello?');
    http.expectOne('/api/chat/route').flush('down', { status: 500, statusText: 'Server Error' });
    http.expectOne('/api/ask').flush(ANSWER);
    http.verify();
  });

  it('gives admins Auto, Agent and Docs, and a forced mode skips routing', async () => {
    const { fixture, http } = await setup({ customer: null, can_choose: true });
    http.expectOne('/api/tier1/customers').flush([]);
    fixture.detectChanges();
    const select = (fixture.nativeElement as HTMLElement).querySelector('select[aria-label="Mode (admin)"]');
    expect(Array.from(select?.querySelectorAll('option') ?? []).map(o => o.textContent?.trim())).toEqual(['Auto', 'Agent', 'Docs']);

    fixture.componentInstance.chatMode = 'rag';
    ask(fixture, 'What does ERR-4032 mean?');
    http.expectNone('/api/chat/route');
    http.expectOne('/api/ask').flush(ANSWER);
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('.routed-from')).toBeNull();
    http.verify();
  });
});
