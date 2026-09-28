import {
  Component,
  ElementRef,
  ViewChild,
  AfterViewChecked,
  OnDestroy,
} from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ChatService, Message, AskResponse } from '../../services/chat.service';
import { AgentChatService, AgentStep, AgentResult } from '../../services/agent-chat.service';

interface QuestionItem {
  id: string;
  text: string;
  notInCorpus?: boolean;
}

interface QuestionGroup {
  label: string;
  questions: QuestionItem[];
  mode: 'rag' | 'agent' | 'both';
}

interface AgentTurn {
  steps: AgentStep[];
  result: AgentResult | null;
  jobId: string;
  status: 'running' | 'done' | 'error';
  error: string | null;
  expandedResults: Set<string>;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
  response?: AskResponse;
  agentTurn?: AgentTurn;
}

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule, DecimalPipe],
  templateUrl: './chat.component.html',
  styleUrl: './chat.component.scss',
})
export class ChatComponent implements AfterViewChecked, OnDestroy {
  @ViewChild('messagesEnd') private messagesEnd!: ElementRef;
  @ViewChild('inputField') private inputField!: ElementRef;

  messages: ChatMessage[] = [];
  inputText = '';
  loading = false;
  expandedChunks: Set<number> = new Set();
  hybridMode = true;
  chatMode: 'rag' | 'agent' = 'rag';
  tightBudget = false;

  openGroups: Set<string> = new Set(['Error Codes']);

  private _pollTimer: ReturnType<typeof setInterval> | null = null;

  questionGroups: QuestionGroup[] = [
    {
      label: 'Error Codes',
      mode: 'rag',
      questions: [
        { id: 'Q1', text: 'What does ERR-4032 mean?' },
        { id: 'Q2', text: 'What does ERR-5010 mean?' },
        { id: 'Q3', text: 'How do I fix ERR-4040?' },
        { id: 'Q4', text: 'How do I fix ERR-6030?' },
        { id: 'Q9', text: 'What causes PAY-1001?' },
      ],
    },
    {
      label: 'Migration & Roles',
      mode: 'rag',
      questions: [
        { id: 'Q5',  text: 'How do I request a migration rollback?' },
        { id: 'Q6',  text: 'What happens to auto-pay during a billing migration?' },
        { id: 'Q7',  text: 'Which account roles can confirm a billing migration?' },
        { id: 'Q8',  text: 'Can a completed billing migration be rolled back?' },
        { id: 'Q10', text: 'What does PLAN-ENT-V1 map to on the new platform?' },
      ],
    },
    {
      label: 'Not-In-Corpus',
      mode: 'rag',
      questions: [
        { id: 'Q11', text: 'Can I get a refund if my billing migration fails?', notInCorpus: true },
        { id: 'Q12', text: 'What is the processing fee for international credit card payments?', notInCorpus: true },
      ],
    },
    {
      label: 'Standard Tickets',
      mode: 'agent',
      questions: [
        { id: 'T002', text: 'Please resolve ticket T002 for customer C102.' },
        { id: 'T003', text: 'Please resolve ticket T003 for customer C103.' },
        { id: 'T004', text: 'Please resolve ticket T004 for customer C104.' },
        { id: 'T007', text: 'Please resolve ticket T007 for customer C107.' },
      ],
    },
    {
      label: 'Branching Tickets ★',
      mode: 'agent',
      questions: [
        { id: 'T008', text: 'Please resolve ticket T008 for customer C108.' },
        { id: 'T009', text: 'Please resolve ticket T009 for customer C109.' },
        { id: 'T010', text: 'Please resolve ticket T010 for customer C110.' },
      ],
    },
    {
      label: 'Adversarial Tickets ⚠',
      mode: 'agent',
      questions: [
        { id: 'T011', text: 'Please resolve ticket T011 for customer C111.' },
        { id: 'T012', text: 'Please resolve ticket T012 for customer C112.' },
        { id: 'T013', text: 'Please resolve ticket T013 for customer C113.' },
      ],
    },
    {
      label: 'Freeform',
      mode: 'agent',
      questions: [
        { id: 'F1', text: 'What is your refund policy for enterprise customers?' },
        { id: 'F2', text: 'How long does a refund take to process?' },
        { id: 'F3', text: 'Can I get a refund for order O201?' },
      ],
    },
  ];

  get visibleGroups(): QuestionGroup[] {
    return this.questionGroups.filter(g => g.mode === this.chatMode || g.mode === 'both');
  }

  constructor(
    private chatService: ChatService,
    private agentSvc: AgentChatService,
  ) {}

  ngOnDestroy(): void {
    this._stopPolling();
  }

  toggleGroup(label: string): void {
    const next = new Set(this.openGroups);
    if (next.has(label)) next.delete(label);
    else next.add(label);
    this.openGroups = next;
  }

  isGroupOpen(label: string): boolean {
    return this.openGroups.has(label);
  }

  useQuestion(text: string): void {
    this.inputText = text;
    setTimeout(() => this.inputField?.nativeElement?.focus(), 0);
  }

  get sessionP50Ms(): number | null {
    const vals = this.messages
      .filter(m => m.role === 'assistant' && m.response)
      .map(m => m.response!.total_ms);
    if (!vals.length) return null;
    const sorted = [...vals].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 === 0
      ? Math.round((sorted[mid - 1] + sorted[mid]) / 2)
      : sorted[mid];
  }

  scoreLabel(retriever: string): string {
    return retriever === 'hybrid-bm25-rrf' ? 'rrf' : 'sim';
  }

  ngAfterViewChecked(): void {
    this.scrollToBottom();
  }

  sendMessage(): void {
    const question = this.inputText.trim();
    if (!question || this.loading) return;
    this.inputText = '';

    if (this.chatMode === 'agent') {
      this._sendAgentMessage(question);
    } else {
      this._sendRagMessage(question);
    }
  }

  private _sendRagMessage(question: string): void {
    this.messages.push({ role: 'user', text: question });
    this.loading = true;

    this.chatService.ask(question, this.hybridMode).subscribe({
      next: (response: AskResponse) => {
        this.messages.push({ role: 'assistant', text: response.answer, response });
        this.loading = false;
      },
      error: () => {
        this.messages.push({ role: 'assistant', text: 'Something went wrong. Please try again.' });
        this.loading = false;
      },
    });
  }

  private _sendAgentMessage(msg: string): void {
    const ticketMatch = msg.match(/\bT\d{3}\b/i);
    // Only auto-route to ticket-resolution mode for short references (e.g. "T008",
    // "resolve ticket T008"). A longer natural-language question that happens to
    // mention a ticket ID (e.g. "show me the escalation history for T008") should
    // stay freeform so the agent can reach for tools beyond the refund verdict flow.
    const wordCount = msg.trim().split(/\s+/).length;
    const ticketId = ticketMatch && wordCount <= 4 ? ticketMatch[0].toUpperCase() : undefined;

    const agentTurn: AgentTurn = {
      steps: [],
      result: null,
      jobId: '',
      status: 'running',
      error: null,
      expandedResults: new Set(),
    };

    this.messages.push({ role: 'user', text: msg });
    this.messages.push({ role: 'assistant', text: '', agentTurn });
    this.loading = true;

    const body: Record<string, unknown> = { tight_budget: this.tightBudget };
    if (ticketId) body['ticket_id'] = ticketId;
    else body['message'] = msg;

    this.agentSvc.startRunRaw(body).subscribe({
      next: (r) => {
        agentTurn.jobId = r.job_id;
        this._startPolling();
      },
      error: (e) => {
        agentTurn.status = 'error';
        agentTurn.error = e?.error?.detail ?? 'Failed to start agent.';
        this.loading = false;
      },
    });
  }

  private _startPolling(): void {
    if (this._pollTimer) return;
    this._pollTimer = setInterval(() => this._pollRunning(), 600);
  }

  private _stopPolling(): void {
    if (this._pollTimer) { clearInterval(this._pollTimer); this._pollTimer = null; }
  }

  private _pollRunning(): void {
    const agentMessages = this.messages.filter(m => m.agentTurn?.status === 'running' && m.agentTurn.jobId);
    if (!agentMessages.length) { this._stopPolling(); this.loading = false; return; }

    for (const m of agentMessages) {
      const turn = m.agentTurn!;
      this.agentSvc.getStatus(turn.jobId).subscribe({
        next: (s) => {
          turn.steps = s.steps;
          if (s.status === 'done') {
            turn.status = 'done';
            turn.result = s.result;
            this.loading = false;
          } else if (s.status === 'error') {
            turn.status = 'error';
            turn.error = s.error ?? 'Agent run failed.';
            this.loading = false;
          }
        },
        error: () => {
          // Transient network error — keep polling; job will time out server-side
        },
      });
    }
  }

  toggleChunks(index: number): void {
    if (this.expandedChunks.has(index)) this.expandedChunks.delete(index);
    else this.expandedChunks.add(index);
  }

  isExpanded(index: number): boolean {
    return this.expandedChunks.has(index);
  }

  toggleAgentResult(turn: AgentTurn, key: string): void {
    if (turn.expandedResults.has(key)) turn.expandedResults.delete(key);
    else turn.expandedResults.add(key);
  }

  toolColor(tool: string): string {
    const map: Record<string, string> = {
      get_ticket: 'tool-ticket',
      get_order: 'tool-order',
      get_customer_tier: 'tool-tier',
      search_knowledge_base: 'tool-kb',
    };
    return map[tool] ?? 'tool-default';
  }

  resultPreview(result: Record<string, unknown>): string {
    const s = JSON.stringify(result);
    return s.length > 120 ? s.slice(0, 120) + '...' : s;
  }

  resultFull(result: Record<string, unknown>): string {
    return JSON.stringify(result, null, 2);
  }

  onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.sendMessage();
    }
  }

  private scrollToBottom(): void {
    try { this.messagesEnd.nativeElement.scrollIntoView({ behavior: 'smooth' }); } catch {}
  }
}
