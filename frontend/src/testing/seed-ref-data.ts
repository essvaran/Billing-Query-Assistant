import seed from '../../../data/seed/reference.json';
import { RefCategory, setRefData } from '../app/shared/ref-data';

type SeedCategory = Partial<RefCategory> & { default_meta?: Record<string, unknown>; values?: Record<string, unknown>[] };

/**
 * Fill the reference store from the same seed file the catalog DB is created from, so specs check the labels a
 * fresh install shows instead of a second copy typed into the tests.
 */
export function loadSeedRefData(settings: Record<string, unknown> = {}): void {
  const list = ((seed as unknown as { categories: SeedCategory[] }).categories).map(c => ({
    category: c.category!, label: c.label ?? c.category!, description: c.description ?? '',
    codes_editable: c.codes_editable ?? true, meta_schema: c.meta_schema ?? {},
    values: (c.values ?? []).map((v, i) => ({
      code: String(v['code']), label: String(v['label'] ?? v['code']), description: String(v['description'] ?? ''),
      active: v['active'] !== false, system: !!v['system'], sort_order: i,
      meta: { ...(c.default_meta ?? {}), ...((v['meta'] as Record<string, unknown>) ?? {}) },
    })),
  })) as RefCategory[];
  setRefData(list, settings);
}
