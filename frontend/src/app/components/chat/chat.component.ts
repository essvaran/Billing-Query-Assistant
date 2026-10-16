import {
  Component,
  ElementRef,
  ViewChild,
  AfterViewChecked,
  OnDestroy,
  OnInit,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ChatService, Message, AskResponse, FeedbackReason } from '../../services/chat.service';
import { AgentChatService, AgentStep, AgentResult } from '../../services/agent-chat.service';

interface AgentTurn {
  steps: AgentStep[];
  result: AgentResult | null;
  jobId: string;
  status: 'running' | 'done' | 'error';
  error: string | null;
}

interface FeedbackState {
  rating: 'up' | 'down' | null;
  formOpen: boolean;
  reason: string;
  comment: string;
  busy: boolean;
  error: string | null;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
  response?: AskResponse;
  agentTurn?: AgentTurn;
  feedback?: FeedbackState;
}

const DEFAULT_REASONS: FeedbackReason[] = [
  { code: 'wrong_answer', label: 'The answer is wrong' },
  { code: 'not_helpful', label: 'It did not answer my question' },
  { code: 'incomplete', label: 'Important information is missing' },
  { code: 'outdated', label: 'The information is outdated' },
  { code: 'unclear', label: 'Hard to understand' },
  { code: 'other', label: 'Something else' },
];

const _TOOL_LABELS: Record<string, string> = {
  get_ticket: 'Checked ticket',
  get_order: 'Fetched order',
  get_customer_tier: 'Checked customer tier',
  search_knowledge_base: 'Searched knowledge base',
};

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './chat.component.html',
  styleUrl: './chat.component.scss',
})
export class ChatComponent implements OnInit, AfterViewChecked, OnDestroy {
  @ViewChild('messagesEnd') private messagesEnd!: ElementRef;
  @ViewChild('inputField') private inputField!: ElementRef;

  messages: ChatMessage[] = [];
  inputText = '';
  loading = false;
  expandedChunks: Set<number> = new Set();
  chatMode: 'rag' | 'agent' = 'rag';
  reasons: FeedbackReason[] = DEFAULT_REASONS;

  private _pollTimer: ReturnType<typeof setInterval> | null = null;
  private _expandedTools = new Map<string, boolean>();

  constructor(
    private chatService: ChatService,
    private agentSvc: AgentChatService,
  ) {}

  ngOnInit(): void {
    this.chatService.feedbackReasons().subscribe({
      next: this.onReasons.bind(this),
      error: this.noop.bind(this),
    });
  }

  private onReasons(list: FeedbackReason[]): void {
    if (list && list.length > 0) {
      this.reasons = list;
    }
  }

  private noop(): void {
    // The built-in reason list is used when the API cannot be reached.
  }

  ngOnDestroy(): void {
    this._stopPolling();
  }

  // ------------------------------------------------------------ feedback (thumbs up or down)

  canRate(msg: ChatMessage): boolean {
    return !!msg.feedback && !!msg.response && !!msg.response.trace_id;
  }

  thumbsUp(msg: ChatMessage): void {
    const fb = msg.feedback;
    if (!fb || fb.busy || fb.rating === 'up') {
      return;
    }
    fb.formOpen = false;
    this.sendFeedback(msg, 'up');
  }

  thumbsDown(msg: ChatMessage): void {
    const fb = msg.feedback;
    if (!fb || fb.busy || fb.rating === 'down') {
      return;
    }
    fb.error = null;
    fb.formOpen = true;
  }

  cancelFeedback(msg: ChatMessage): void {
    if (msg.feedback) {
      msg.feedback.formOpen = false;
      msg.feedback.error = null;
    }
  }

  submitThumbsDown(msg: ChatMessage): void {
    const fb = msg.feedback;
    if (!fb || fb.busy) {
      return;
    }
    if (!fb.reason) {
      fb.error = 'Please choose a reason so we can fix it.';
      return;
    }
    this.sendFeedback(msg, 'down');
  }

  private sendFeedback(msg: ChatMessage, rating: 'up' | 'down'): void {
    const fb = msg.feedback;
    if (!fb || !msg.response || !msg.response.trace_id) {
      return;
    }
    fb.busy = true;
    fb.error = null;
    const payload = {
      trace_id: msg.response.trace_id,
      rating: rating,
      reason_code: rating === 'down' ? fb.reason : undefined,
      comment: rating === 'down' ? fb.comment.trim() || undefined : undefined,
    };
    this.chatService.sendFeedback(payload).subscribe({
      next: this.onFeedbackSaved.bind(this, msg, rating),
      error: this.onFeedbackError.bind(this, msg),
    });
  }

  private onFeedbackSaved(msg: ChatMessage, rating: 'up' | 'down'): void {
    if (msg.feedback) {
      msg.feedback.busy = false;
      msg.feedback.rating = rating;
      msg.feedback.formOpen = false;
    }
  }

  private onFeedbackError(msg: ChatMessage, err: { error?: { detail?: unknown } }): void {
    if (msg.feedback) {
      msg.feedback.busy = false;
      const detail = err && err.error ? err.error.detail : null;
      msg.feedback.error = typeof detail === 'string' ? detail : 'Could not send your feedback. Please try again.';
    }
  }

  private newFeedbackState(): FeedbackState {
    return { rating: null, formOpen: false, reason: '', comment: '', busy: false, error: null };
  }

  ngAfterViewChecked(): void {
    this.scrollToBottom();
  }

  toolSteps(steps: AgentStep[]): AgentStep[] {
    return steps.filter(s => s.type === 'tool_call');
  }

  toolPairs(steps: AgentStep[]): Array<{ call: AgentStep; result: AgentStep | null }> {
    const pairs: Array<{ call: AgentStep; result: AgentStep | null }> = [];
    for (let i = 0; i < steps.length; i++) {
      if (steps[i].type === 'tool_call') {
        const next = steps[i + 1];
        pairs.push({ call: steps[i], result: next?.type === 'tool_result' ? next : null });
      }
    }
    return pairs;
  }

  friendlyTool(tool: string): string {
    return _TOOL_LABELS[tool] ?? tool;
  }

  toolArg(step: AgentStep): string {
    if (!step.args) return '';
    const vals = Object.values(step.args);
    if (!vals.length) return '';
    const first = String(vals[0]);
    return first.length <= 24 ? first : first.slice(0, 21) + '...';
  }

  resultSummary(step: AgentStep): string {
    const r = step.result;
    if (!r) return '';
    if (r['not_found']) return 'Not found';
    if (r['error']) return String(r['error']).slice(0, 60);
    if ('ticket_id' in r && 'customer_id' in r)
      return `Customer ${r['customer_id']} | Order ${r['order_id']}`;
    if ('order_id' in r && 'amount' in r)
      return `$${r['amount']} ${r['currency'] ?? ''} | ${r['days_since_purchase']}d ago | ${r['fulfilment_status'] ?? r['status'] ?? ''}`;
    if ('tier' in r && 'refund_days' in r)
      return `${r['tier']} tier | ${r['refund_days']}-day refund window`;
    if (Array.isArray(r['results']))
      return `${(r['results'] as unknown[]).length} result${(r['results'] as unknown[]).length !== 1 ? 's' : ''} found`;
    return '';
  }

  formatResultJson(step: AgentStep): string {
    if (!step.result) return '';
    const s = JSON.stringify(step.result, null, 2);
    return s.length > 600 ? s.slice(0, 597) + '...' : s;
  }

  toggleToolResult(msgIdx: number, pairIdx: number): void {
    const key = `${msgIdx}-${pairIdx}`;
    this._expandedTools.set(key, !this._expandedTools.get(key));
  }

  isToolExpanded(msgIdx: number, pairIdx: number): boolean {
    return !!this._expandedTools.get(`${msgIdx}-${pairIdx}`);
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

    this.chatService.ask(question, true).subscribe({
      next: (response: AskResponse) => {
        this.messages.push({
          role: 'assistant',
          text: response.answer,
          response,
          feedback: response.trace_id ? this.newFeedbackState() : undefined,
        });
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
    const wordCount = msg.trim().split(/\s+/).length;
    const ticketId = ticketMatch && wordCount <= 4 ? ticketMatch[0].toUpperCase() : undefined;

    const agentTurn: AgentTurn = {
      steps: [],
      result: null,
      jobId: '',
      status: 'running',
      error: null,
    };

    this.messages.push({ role: 'user', text: msg });
    this.messages.push({ role: 'assistant', text: '', agentTurn });
    this.loading = true;

    const body: Record<string, unknown> = { tight_budget: false };
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
          // Transient network error -- keep polling
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
