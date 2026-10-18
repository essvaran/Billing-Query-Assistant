import { Component, OnInit, OnDestroy, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  TrajectoryService,
  TrajectoryEvalReport,
  MitigationReport,
  ExpectedSequenceEntry,
  EvalStatus,
  InjectionResult,
  TrajectoryResult,
} from '../../services/trajectory.service';

type Tab = 'sequences' | 'results' | 'gap' | 'mitigation' | 'regression' | 'security';

@Component({
  selector: 'app-trajectory',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './trajectory.component.html',
  styleUrl: './trajectory.component.scss',
})
export class TrajectoryComponent implements OnInit, OnDestroy {
  private svc = inject(TrajectoryService);

  activeTab: Tab = 'sequences';
  tabs: { key: Tab; label: string }[] = [
    { key: 'sequences', label: 'Expected Sequences' },
    { key: 'results', label: 'Results' },
    { key: 'gap', label: 'Gap Analysis' },
    { key: 'mitigation', label: 'Mitigation' },
    { key: 'regression', label: 'Regression' },
  ];

  sequences: ExpectedSequenceEntry[] = [];
  report: TrajectoryEvalReport | null = null;
  mitigationReport: MitigationReport | null = null;
  injectionResults: InjectionResult[] = [];

  evalStatus: EvalStatus = { status: 'idle', started_at: null, error: null };
  mitigationStatus: EvalStatus = { status: 'idle', started_at: null, error: null };
  injectionStatus: EvalStatus = { status: 'idle', started_at: null, error: null };

  expandedTickets: Set<string> = new Set();
  expandedMitigationTickets: Set<string> = new Set();

  private evalPoll: ReturnType<typeof setInterval> | null = null;
  private mitigationPoll: ReturnType<typeof setInterval> | null = null;
  private injectionPoll: ReturnType<typeof setInterval> | null = null;

  ngOnInit() {
    this.loadSequences();
    this.loadResults();
    this.loadMitigationResults();
    this.loadInjectionResults();
  }

  ngOnDestroy() {
    this.stopAllPolls();
  }

  adversarialIds(): string { return this.sequences.filter((s: any) => s.adversarial).map((s: any) => s.ticket_id).join(', '); }

  selectTab(tab: Tab) {
    this.activeTab = tab;
  }

  loadSequences() {
    this.svc.getExpectedSequences().subscribe({
      next: (data) => (this.sequences = data),
      error: () => {},
    });
  }

  loadResults() {
    this.svc.getResults().subscribe({
      next: (data) => (this.report = data),
      error: () => {},
    });
  }

  loadMitigationResults() {
    this.svc.getMitigationResults().subscribe({
      next: (data) => (this.mitigationReport = data),
      error: () => {},
    });
  }

  loadInjectionResults() {
    this.svc.getInjectionResults().subscribe({
      next: (data) => (this.injectionResults = data),
      error: () => {},
    });
  }

  // --- Eval run ---
  startEval() {
    this.svc.startEval().subscribe({
      next: () => {
        this.evalStatus = { status: 'running', started_at: new Date().toISOString(), error: null };
        this.startEvalPoll();
      },
      error: (err) => {
        this.evalStatus = { status: 'error', started_at: null, error: err.message };
      },
    });
  }

  private startEvalPoll() {
    this.evalPoll = setInterval(() => {
      this.svc.getStatus().subscribe({
        next: (s) => {
          this.evalStatus = s;
          if (s.status === 'done' || s.status === 'error') {
            this.stopEvalPoll();
            if (s.status === 'done') this.loadResults();
          }
        },
      });
    }, 5000);
  }

  private stopEvalPoll() {
    if (this.evalPoll) {
      clearInterval(this.evalPoll);
      this.evalPoll = null;
    }
  }

  // --- Mitigation run ---
  startMitigation() {
    this.svc.startMitigation().subscribe({
      next: () => {
        this.mitigationStatus = { status: 'running', started_at: new Date().toISOString(), error: null };
        this.startMitigationPoll();
      },
      error: (err) => {
        this.mitigationStatus = { status: 'error', started_at: null, error: err.message };
      },
    });
  }

  private startMitigationPoll() {
    this.mitigationPoll = setInterval(() => {
      this.svc.getMitigationStatus().subscribe({
        next: (s) => {
          this.mitigationStatus = s;
          if (s.status === 'done' || s.status === 'error') {
            this.stopMitigationPoll();
            if (s.status === 'done') this.loadMitigationResults();
          }
        },
      });
    }, 5000);
  }

  private stopMitigationPoll() {
    if (this.mitigationPoll) {
      clearInterval(this.mitigationPoll);
      this.mitigationPoll = null;
    }
  }

  // --- Injection run ---
  startInjectionTest() {
    this.svc.startInjectionTest().subscribe({
      next: () => {
        this.injectionStatus = { status: 'running', started_at: new Date().toISOString(), error: null };
        this.startInjectionPoll();
      },
      error: (err) => {
        this.injectionStatus = { status: 'error', started_at: null, error: err.message };
      },
    });
  }

  private startInjectionPoll() {
    this.injectionPoll = setInterval(() => {
      this.svc.getInjectionStatus().subscribe({
        next: (s) => {
          this.injectionStatus = s;
          if (s.status === 'done' || s.status === 'error') {
            this.stopInjectionPoll();
            if (s.status === 'done') this.loadInjectionResults();
          }
        },
      });
    }, 5000);
  }

  private stopInjectionPoll() {
    if (this.injectionPoll) {
      clearInterval(this.injectionPoll);
      this.injectionPoll = null;
    }
  }

  private stopAllPolls() {
    this.stopEvalPoll();
    this.stopMitigationPoll();
    this.stopInjectionPoll();
  }

  toggleTicket(id: string) {
    if (this.expandedTickets.has(id)) {
      this.expandedTickets.delete(id);
    } else {
      this.expandedTickets.add(id);
    }
  }

  toggleMitigationTicket(id: string) {
    if (this.expandedMitigationTickets.has(id)) {
      this.expandedMitigationTickets.delete(id);
    } else {
      this.expandedMitigationTickets.add(id);
    }
  }

  getToolColor(tool: string): string {
    const colors: Record<string, string> = {
      get_ticket: '#6d28d9',
      get_order: '#0e7490',
      get_customer_tier: '#b45309',
      search_knowledge_base: '#15803d',
    };
    return colors[tool] || '#64748b';
  }

  getGapExampleResults(): TrajectoryResult[] {
    if (!this.report) return [];
    return this.report.results.filter(
      (r) => r.outcome_passed && !r.trajectory_passed
    );
  }

  formatPercent(val: number): string {
    return (val * 100).toFixed(1) + '%';
  }

  formatCost(val: number): string {
    return '$' + val.toFixed(6);
  }

  formatDelta(val: number, isPercent = false): string {
    const prefix = val > 0 ? '+' : '';
    if (isPercent) return prefix + (val * 100).toFixed(1) + '%';
    return prefix + val.toFixed(6);
  }
}
