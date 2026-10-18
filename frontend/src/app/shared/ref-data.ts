import { Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of, tap, catchError, forkJoin, map } from 'rxjs';

/**
 * Reference lists and public settings from the catalog (GET /api/catalog/ref, /api/catalog/public-settings).
 * Nothing a person reads in a list, label or default is typed into the frontend: it comes from here, and admins
 * edit it on the Data page. The store is a set of signals, so every template that reads a label updates when an
 * admin changes it and the lists are reloaded.
 */
export interface RefValue {
  code: string;
  label: string;
  description: string;
  sort_order: number;
  active: boolean;
  system: boolean;
  meta: Record<string, unknown>;
  updated_at?: string;
  updated_by?: string;
}

export interface RefCategory {
  category: string;
  label: string;
  description: string;
  codes_editable: boolean;
  meta_schema: Record<string, { type: 'text' | 'int' | 'bool' | 'list'; label: string }>;
  values: RefValue[];
}

const categories = signal<Record<string, RefCategory>>({});
const publicSettings = signal<Record<string, unknown>>({});
const loaded = signal(false);

/** Active values of a list, in their stored order. */
export function refValues(category: string, includeInactive = false): RefValue[] {
  const c = categories()[category];
  return c ? c.values.filter(v => includeInactive || v.active) : [];
}

/** The label of a code; inactive values still label old records. Falls back to the code itself. */
export function refLabel(category: string, code: string | null | undefined, fallback?: string): string {
  if (code === null || code === undefined || code === '') return fallback ?? '';
  return categories()[category]?.values.find(v => v.code === code)?.label ?? fallback ?? code;
}

export function refMeta<T = unknown>(category: string, code: string | null | undefined, key: string): T | undefined {
  if (!code) return undefined;
  return categories()[category]?.values.find(v => v.code === code)?.meta?.[key] as T | undefined;
}

export function refDescription(category: string, code: string | null | undefined): string {
  return (code && categories()[category]?.values.find(v => v.code === code)?.description) || '';
}

export function publicSetting<T>(key: string, fallback: T): T {
  const v = publicSettings()[key];
  return v === undefined ? fallback : (v as T);
}

/** Fill the store directly (the service does this after GET; specs use it with the seed file). */
export function setRefData(list: RefCategory[], settings: Record<string, unknown> = {}): void {
  categories.set(Object.fromEntries(list.map(c => [c.category, c])));
  publicSettings.set(settings);
  loaded.set(true);
}

export const refLoaded = loaded.asReadonly();
export const refCategories = categories.asReadonly();

@Injectable({ providedIn: 'root' })
export class RefDataService {
  private http = inject(HttpClient);
  readonly loaded = loaded.asReadonly();
  readonly categoryList = computed(() => Object.values(categories()).sort((a, b) => a.label.localeCompare(b.label)));

  /** Load (or reload after an edit) every list and the public settings. Safe to call repeatedly. */
  load(): Observable<boolean> {
    return forkJoin({
      ref: this.http.get<RefCategory[]>('/api/catalog/ref'),
      settings: this.http.get<Record<string, unknown>>('/api/catalog/public-settings').pipe(catchError(() => of({}))),
    }).pipe(
      tap(({ ref, settings }) => setRefData(ref, settings)),
      map(() => true),
      catchError(() => of(false)),
    );
  }

  /** Clear on sign-out so the next user does not see stale lists. */
  clear(): void { categories.set({}); publicSettings.set({}); loaded.set(false); }
}
