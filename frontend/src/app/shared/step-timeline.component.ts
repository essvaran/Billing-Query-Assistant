import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { Step } from '../services/tier1.service';
import { refLabel, refMeta } from './ref-data';

interface Row { key: string; title: string; detail: string; state: 'running' | 'ok' | 'error' | 'blocked' }

// Tool titles are the catalog list tier1_tool (label = done, meta.running = in progress).
const toolTitle = (tool: string): string => refLabel('tier1_tool', tool);
const toolRunning = (tool: string): string => refMeta<string>('tier1_tool', tool, 'running') ?? refLabel('tier1_tool', tool);

function summarise(tool: string, result: Record<string, unknown> | undefined): string {
  if (!result) return '';
  if (result['error']) return String(result['error']).replace(/_/g, ' ');
  if (tool === 'check_entitlement') {
    const check = result['refund_check'] as Record<string, unknown> | undefined;
    const base = `${result['policy_version']} policy, ${result['refund_days']}-day window`;
    return check && check['days_since_purchase'] !== undefined
      ? `${base}; order is ${check['days_since_purchase']} days old` : base;
  }
  if (tool === 'lookup_order') return `${result['status']}, ${result['days_since_purchase']} days since purchase`;
  if (tool === 'search_help_centre') {
    const n = (result['results'] as unknown[] | undefined)?.length ?? 0;
    const filter = result['policy_version_filter'];
    return `${n} source${n === 1 ? '' : 's'}` + (filter ? `, only the ${filter} policy` : '');
  }
  if (tool === 'escalate') return 'handoff queued';
  return '';
}

/** "How I got here": each step the assistant took, in plain words. Live while the job runs.
 *  audience 'customer' shows only what a customer needs (which checks ran and whether the answer was checked),
 *  never safety-check categories, violation codes, limits or policy codes. The API also sends a customer only
 *  progress fields, so this is the second of two layers. */
@Component({
  selector: 'app-step-timeline',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <ol class="steps" aria-live="polite" aria-label="Steps the assistant took">
      @for (row of rows; track row.key) {
        <li class="step" [attr.data-state]="row.state">
          <span class="step__mark" aria-hidden="true"></span>
          <div>
            <div class="step__title">{{ row.title }}</div>
            @if (row.detail) { <div class="step__detail">{{ row.detail }}</div> }
          </div>
        </li>
      }
      @if (running) {
        <li class="step" data-state="running"><span class="step__mark" aria-hidden="true"></span>
          <div class="step__title">Working</div></li>
      }
      @if (!rows.length && !running) { <li class="step__none">No steps recorded yet.</li> }
    </ol>`,
  styles: [`
    .steps { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: .15rem; }
    .step { display: flex; gap: .65rem; padding: .45rem 0; position: relative; }
    .step:not(:last-child)::before { content: ''; position: absolute; left: .32rem; top: 1.35rem; bottom: -.3rem; width: 1px; background: var(--border-strong); }
    .step__mark { width: .7rem; height: .7rem; border-radius: 50%; margin-top: .3rem; flex-shrink: 0; border: 2px solid var(--text-muted); background: var(--surface-card); }
    [data-state='ok'] .step__mark { background: var(--success); border-color: var(--success); }
    [data-state='error'] .step__mark { background: var(--danger); border-color: var(--danger); }
    [data-state='blocked'] .step__mark { background: var(--warning); border-color: var(--warning); }
    [data-state='running'] .step__mark { border-color: var(--accent); animation: pulse 1.1s ease-in-out infinite; }
    @keyframes pulse { 50% { box-shadow: 0 0 0 4px rgba(137,180,250,.25); } }
    @media (prefers-reduced-motion: reduce) { [data-state='running'] .step__mark { animation: none; } }
    .step__title { font-size: .85rem; font-weight: 600; }
    .step__detail { font-size: .78rem; color: var(--text-secondary); margin-top: .1rem; overflow-wrap: anywhere; }
    .step__none { font-size: .82rem; color: var(--text-muted); }
  `],
})
export class StepTimelineComponent {
  @Input() steps: Step[] = [];
  @Input() running = false;
  @Input() audience: 'customer' | 'admin' = 'admin';

  get rows(): Row[] {
    return this.audience === 'customer' ? this.customerRows() : this.adminRows();
  }

  private customerRows(): Row[] {
    const rows: Row[] = [];
    const open = new Map<string, Row>();
    this.steps.forEach((s, i) => {
      if (s.type === 'guard' && s.stage === 'pre') {
        rows.push(s.blocked
          ? { key: `g${i}`, title: 'Passed to our team', detail: 'A person will reply to this one', state: 'blocked' }
          : { key: `g${i}`, title: 'Read your message', detail: '', state: 'ok' });
      } else if (s.type === 'tool_call' && s.tool) {
        const row: Row = { key: `t${i}`, title: toolRunning(s.tool) ?? 'Checking', detail: '', state: 'running' };
        open.set(s.tool, row);
        rows.push(row);
      } else if (s.type === 'tool_result' && s.tool) {
        const row = open.get(s.tool);
        if (row) {
          row.title = toolTitle(s.tool) ?? 'Checked';
          row.state = s.failed || s.result?.['error'] ? 'error' : 'ok';
          open.delete(s.tool);
        }
      } else if (s.type === 'guard' && s.stage === 'post') {
        rows.push(s.blocked || (s.violations ?? []).length
          ? { key: `p${i}`, title: 'Sent to a person to review', detail: '', state: 'blocked' }
          : { key: `p${i}`, title: 'Answer checked against the help centre', detail: '', state: 'ok' });
      } else if (s.type === 'budget_hit') {
        rows.push({ key: `b${i}`, title: 'Passed to our team', detail: 'This one needs a person', state: 'blocked' });
      }
    });
    return rows;
  }

  private adminRows(): Row[] {
    const rows: Row[] = [];
    const open = new Map<string, Row>();
    this.steps.forEach((s, i) => {
      if (s.type === 'guard' && s.stage === 'pre') {
        rows.push(s.blocked
          ? { key: `g${i}`, title: 'Safety check stopped the assistant', detail: (s.category ?? '').replace(/_/g, ' '), state: 'blocked' }
          : { key: `g${i}`, title: 'Safety check passed', detail: 'No legal, fraud or instruction-like text found', state: 'ok' });
      } else if (s.type === 'tool_call' && s.tool) {
        const row: Row = { key: `t${i}`, title: toolRunning(s.tool) ?? s.tool, detail: '', state: 'running' };
        open.set(s.tool, row);
        rows.push(row);
      } else if (s.type === 'tool_result' && s.tool) {
        const row = open.get(s.tool);
        const failed = !!s.result?.['error'];
        if (row) {
          row.title = toolTitle(s.tool) ?? s.tool;
          row.detail = summarise(s.tool, s.result);
          row.state = failed ? 'error' : 'ok';
          open.delete(s.tool);
        }
      } else if (s.type === 'guard' && s.stage === 'post') {
        const v = s.violations ?? [];
        rows.push(v.length
          ? { key: `p${i}`, title: 'Final checks blocked the draft', detail: v.map(x => x.replace(/_/g, ' ')).join(', '), state: 'blocked' }
          : { key: `p${i}`, title: 'Final checks passed', detail: `${s.citations ?? 0} citation${s.citations === 1 ? '' : 's'} verified`, state: 'ok' });
      } else if (s.type === 'budget_hit') {
        rows.push({ key: `b${i}`, title: 'Stopped: time or budget limit reached', detail: s.budget ?? '', state: 'error' });
      }
    });
    return rows;
  }
}
