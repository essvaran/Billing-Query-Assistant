import { HttpErrorResponse } from '@angular/common/http';

/** The API's own message for a refused write (400/409/422), so the admin sees why. */
export function apiMessage(err: unknown, fallback = 'The change was not saved.'): string {
  const e = err as HttpErrorResponse;
  const detail = (e?.error as { detail?: unknown })?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(-1)[0] ?? ''}: ${d.msg ?? ''}`).join('; ');
  }
  return fallback;
}

/** Shared styles for the Data screens (tables, forms, toolbars). */
export const DATA_STYLES = `
  .bar { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; margin-bottom: .8rem; }
  .grow { flex: 1; }
  .muted { color: var(--text-muted); } .small { font-size: .78rem; }
  .card { background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 1rem 1.1rem; margin-bottom: 1rem; }
  .card h2 { font-size: 1.05rem; margin: 0 0 .3rem; }
  .table-wrap { overflow-x: auto; background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-lg); }
  .tbl { width: 100%; border-collapse: collapse; font-size: .85rem; }
  .tbl th, .tbl td { text-align: left; padding: .5rem .7rem; border-bottom: 1px solid var(--border); vertical-align: top; }
  .tbl tr:last-child td { border-bottom: 0; }
  .tbl th { font-size: .7rem; text-transform: uppercase; letter-spacing: .04em; color: var(--text-muted); white-space: nowrap; }
  .tbl td.actions { white-space: nowrap; text-align: right; }
  .num { text-align: right; }
  .off td { opacity: .55; }
  .pill { display: inline-block; font-size: .7rem; padding: 0 .45rem; border-radius: 999px; border: 1px solid var(--border); color: var(--text-muted); }
  .pill.ok { color: var(--success); border-color: rgba(166,227,161,.4); } .pill.bad { color: var(--danger); border-color: rgba(243,139,168,.4); }
  .pill.warn { color: var(--warning); border-color: rgba(250,179,135,.4); } .pill.accent { color: var(--accent); border-color: rgba(137,180,250,.4); }
  .form { display: grid; gap: .7rem; }
  .form label { display: grid; gap: .25rem; font-size: .85rem; }
  .form .two { display: grid; grid-template-columns: 1fr 1fr; gap: .7rem; }
  .form input, .form select, .form textarea { width: 100%; }
  textarea.code, pre.code { font-family: var(--font-mono, ui-monospace, monospace); font-size: .8rem; }
  pre.code { white-space: pre-wrap; background: var(--surface-base); padding: .7rem; border-radius: var(--radius-md); max-height: 22rem; overflow: auto; margin: 0; }
  .checks { list-style: none; padding: 0; margin: .5rem 0 0; display: grid; gap: .2rem; font-size: .82rem; }
  .checks li[data-ok='true']::before { content: 'Pass: '; color: var(--success); font-weight: 600; }
  .checks li[data-ok='false']::before { content: 'Fail: '; color: var(--danger); font-weight: 600; }
  .err { color: var(--danger); font-size: .84rem; margin: .3rem 0 0; }
  .sk { height: 12rem; }
  @media (max-width: 620px) { .form .two { grid-template-columns: 1fr; } }
`;
