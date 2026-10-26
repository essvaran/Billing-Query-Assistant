import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { LoginComponent, validateLogin } from './login.component';

describe('validateLogin', () => {
  it('accepts a complete sign-in and a complete sign-up', () => {
    expect(validateLogin('signin', '', 'ann@example.com', 'x')).toEqual({});
    expect(validateLogin('signup', 'Ann Lee', ' ann@example.com ', 'long-enough')).toEqual({});
  });

  it('names each missing field instead of one message for all', () => {
    const e = validateLogin('signup', '   ', '', '');
    expect(e.fullName).toBe('Enter your full name.');
    expect(e.email).toBe('Enter your email address.');
    expect(e.password).toBe('Enter your password.');
  });

  it('rejects malformed email addresses the API would reject', () => {
    for (const bad of ['ann', 'ann@', 'ann@example', 'ann@example.c', 'a b@example.com', 'a@b@example.com']) {
      expect(validateLogin('signin', '', bad, 'x').email).withContext(bad).toContain('valid email');
    }
  });

  it('checks password length only when creating an account', () => {
    expect(validateLogin('signup', 'Ann', 'ann@example.com', 'short').password).toBe('Use at least 8 characters.');
    expect(validateLogin('signin', '', 'ann@example.com', 'short').password).toBeUndefined();
  });

  it('counts bytes, not characters, against the 72-byte limit', () => {
    expect(validateLogin('signup', 'Ann', 'ann@example.com', 'a'.repeat(72)).password).toBeUndefined();
    expect(validateLogin('signup', 'Ann', 'ann@example.com', 'é'.repeat(40)).password).toContain('too long');
  });
});

describe('LoginComponent', () => {
  async function setup() {
    await TestBed.configureTestingModule({
      imports: [LoginComponent], providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();
    http.match(() => true).forEach(r => r.flush({ google_client_id: '', password_auth_enabled: true }));
    fixture.detectChanges();
    return { fixture, http, el: fixture.nativeElement as HTMLElement };
  }

  it('shows no errors before the user has done anything', async () => {
    const { el } = await setup();
    expect(el.querySelectorAll('.field-error').length).toBe(0);
  });

  it('shows an error under each invalid field on submit and sends nothing', async () => {
    const { fixture, http, el } = await setup();
    fixture.componentInstance.email = 'not-an-email';
    fixture.componentInstance.submit();
    fixture.detectChanges();
    expect(el.querySelector('#email-error')?.textContent).toContain('valid email');
    expect(el.querySelector('#password-error')?.textContent).toContain('Enter your password');
    expect(el.querySelector('#email')?.getAttribute('aria-invalid')).toBe('true');
    http.expectNone('/api/auth/login');
  });
});
