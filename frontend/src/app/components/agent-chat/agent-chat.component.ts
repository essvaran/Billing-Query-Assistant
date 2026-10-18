import { Component, OnInit, OnDestroy, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { inject } from '@angular/core';
import { refValues } from '../../shared/ref-data';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AgentChatService, AgentStep, AgentResult, TicketInfo } from '../../services/agent-chat.service';
import { environment } from '../../../environments/environment';

interface ChatTurn {
  userMessage: string;
  steps: AgentStep[];
  result: AgentResult | null;
  jobId: string;
  status: 'running' | 'done' | 'error';
  error: string | null;
  expandedResults: Set<string>;
}

@Component({
  selector: 'app-agent-chat',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './agent-chat.component.html',
  styleUrl: './agent-chat.component.scss',
})
export class AgentChatComponent implements OnInit, OnDestroy, AfterViewChecked {
  @ViewChild('feedEnd') private feedEnd!: ElementRef;
  @ViewChild('chatInput') private chatInput!: ElementRef;

  tickets: TicketInfo[] = [];
  ticketsError = false;
  inputText = '';
  tightBudget = false;

  turns: ChatTurn[] = [];

  private _pollTimer: ReturnType<typeof setInterval> | null = null;
  private _shouldScroll = false;

  langfuseUrl = '';
  private http = inject(HttpClient);

  constructor(private svc: AgentChatService) {
    this.http.get<{ langfuse_url?: string }>('/api/obs/meta').subscribe({ next: m => (this.langfuseUrl = m.langfuse_url ?? ''), error: () => {} });
  }

  ngOnInit(): void {
    this.svc.getTickets().subscribe({
      next: t => (this.tickets = t),
      error: () => { this.ticketsError = true; },
    });
  }

  ngOnDestroy(): void { this._stopPolling(); }

  ngAfterViewChecked(): void {
    if (this._shouldScroll) {
      this._scrollFeed();
      this._shouldScroll = false;
    }
  }

  get isRunning(): boolean {
    return this.turns.some(t => t.status === 'running');
  }

  fillTicket(ticket: TicketInfo): void {
    this.inputText = `Please resolve ticket ${ticket.ticket_id} for customer ${ticket.customer_id}.`;
    setTimeout(() => this.chatInput?.nativeElement?.focus(), 50);
  }

  send(): void {
    const msg = this.inputText.trim();
    if (!msg || this.isRunning) return;
    this.inputText = '';

    const ticketMatch = msg.match(/\bT\d{3}\b/i);
    const isTicketMode = !!ticketMatch;
    const ticketId = isTicketMode ? ticketMatch![0].toUpperCase() : undefined;

    const turn: ChatTurn = {
      userMessage: msg,
      steps: [],
      result: null,
      jobId: '',
      status: 'running',
      error: null,
      expandedResults: new Set(),
    };
    this.turns.push(turn);
    this._shouldScroll = true;

    const body: { ticket_id?: string; message?: string; tight_budget: boolean } = {
      tight_budget: this.tightBudget,
    };
    if (isTicketMode && ticketId) body.ticket_id = ticketId;
    else body.message = msg;

    this.svc.startRunRaw(body).subscribe({
      next: r => { turn.jobId = r.job_id; this._startPolling(); },
      error: e => {
        turn.status = 'error';
        turn.error = e?.error?.detail ?? 'Failed to start agent run.';
      },
    });
  }

  onKey(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.send();
    }
  }

  private _startPolling(): void {
    if (this._pollTimer) return;
    this._pollTimer = setInterval(() => this._pollAll(), 600);
  }

  private _stopPolling(): void {
    if (this._pollTimer) { clearInterval(this._pollTimer); this._pollTimer = null; }
  }

  private _pollAll(): void {
    const running = this.turns.filter(t => t.status === 'running' && t.jobId);
    if (!running.length) { this._stopPolling(); return; }

    for (const turn of running) {
      this.svc.getStatus(turn.jobId).subscribe({
        next: s => {
          const prevLen = turn.steps.length;
          turn.steps = s.steps;
          if (turn.steps.length !== prevLen) this._shouldScroll = true;
          if (s.status === 'done') {
            turn.status = 'done';
            turn.result = s.result;
            this._shouldScroll = true;
          } else if (s.status === 'error') {
            turn.status = 'error';
            turn.error = s.error ?? 'Agent run failed.';
          }
        },
        error: () => {
          // transient network error — keep polling, do not mark as failed
        },
      });
    }
  }

  private _scrollFeed(): void {
    try { this.feedEnd?.nativeElement?.scrollIntoView({ behavior: 'smooth' }); } catch {}
  }

  toggleResult(turn: ChatTurn, key: string): void {
    if (turn.expandedResults.has(key)) turn.expandedResults.delete(key);
    else turn.expandedResults.add(key);
  }

  toolColor(tool: string): string {
    const map: Record<string, string> = {
      get_ticket: 'tool-ticket',
      get_order: 'tool-order',
      get_customer_tier: 'tool-tier',
      search_knowledge_base: 'tool-search',
    };
    return map[tool] ?? 'tool-default';
  }

  resultPreview(result: Record<string, unknown>): string {
    const s = JSON.stringify(result);
    return s.length > 140 ? s.slice(0, 140) + '…' : s;
  }

  resultFull(result: Record<string, unknown>): string {
    return JSON.stringify(result, null, 2);
  }

  get suggestedQuestions(): string[] { return refValues('agent_suggestion').map(v => v.label); }
}
