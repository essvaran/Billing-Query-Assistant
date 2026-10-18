import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { HelpComponent, inlineParts } from './help.component';

describe('inlineParts', () => {
  it('splits code and bold spans and keeps the rest as text', () => {
    expect(inlineParts('Run `make up` and press **Enter**.')).toEqual([
      { kind: 'text', text: 'Run ' }, { kind: 'code', text: 'make up' }, { kind: 'text', text: ' and press ' },
      { kind: 'bold', text: 'Enter' }, { kind: 'text', text: '.' },
    ]);
  });
});

describe('HelpComponent', () => {
  it('renders the sections the server sent, as text, never as HTML', async () => {
    await TestBed.configureTestingModule({
      imports: [HelpComponent], providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(HelpComponent);
    fixture.detectChanges();
    http.expectOne('/api/help').flush({
      title: 'Guide', role: 'user', sections: [{
        id: 'start', title: 'Start here', roles: ['user', 'admin'], blocks: [
          { type: 'paragraph', text: 'Hello <img src=x onerror=alert(1)> **world**' },
          { type: 'list', ordered: true, items: ['One', 'Two'] },
          { type: 'table', header: ['A'], rows: [['1']] },
        ],
      }],
    });
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('h2')?.textContent).toBe('Start here');
    expect(el.querySelector('img')).toBeNull();                  // markup in the guide stays text
    expect(el.textContent).toContain('<img src=x onerror=alert(1)>');
    expect(el.querySelector('strong')?.textContent).toBe('world');
    expect(el.querySelectorAll('ol li').length).toBe(2);
    expect(el.querySelector('td')?.textContent?.trim()).toBe('1');
    http.verify();
  });
});
