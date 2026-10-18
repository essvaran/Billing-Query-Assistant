import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { AppComponent } from './app.component';
import { AuthService } from './services/auth.service';
import { ThemeService } from './services/theme.service';

// The Angular scaffold's original specs asserted a `title` and a "Hello, frontend" heading that this app
// never had, so they could not compile. These check what the shell actually does.
describe('AppComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: [provideHttpClient(), provideRouter([])],
    }).compileComponents();
  });

  it('should create the app', () => {
    expect(TestBed.createComponent(AppComponent).componentInstance).toBeTruthy();
  });

  function nav(admin: boolean): string {
    TestBed.overrideProvider(AuthService, { useValue: { isAdmin: admin, currentUser: { email: 'x@example.com' }, logout: () => undefined } });
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('[aria-live="polite"]')).not.toBeNull();
    return el.textContent ?? '';
  }

  it('shows a regular user the chat and nothing else', () => {
    const text = nav(false);
    expect(text).toContain('Chat');
    for (const label of ['Tickets', 'Escalations', 'Try a ticket', 'Insights', 'Admin']) expect(text).not.toContain(label);
  });

  it('shows an admin the operations links as well', () => {
    const text = nav(true);
    for (const label of ['Chat', 'Tickets', 'Escalations', 'Try a ticket', 'Insights', 'Admin']) expect(text).toContain(label);
  });

  it('toggles between dark and light and records the choice on the page', () => {
    const theme = TestBed.inject(ThemeService);
    const before = theme.theme();
    theme.toggle();
    expect(theme.theme()).not.toBe(before);
    expect(document.documentElement.getAttribute('data-theme')).toBe(theme.theme());
    theme.toggle();
    expect(theme.theme()).toBe(before);
  });
});
