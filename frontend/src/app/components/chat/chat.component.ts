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
import { Subscription } from 'rxjs';
import { ChatService, AskResponse, FeedbackReason } from '../../services/chat.service';
import { CustomerOption, PolicyVersion, Step, TicketAnswer, Tier1Service } from '../../services/tier1.service';
import { StepTimelineComponent } from '../../shared/step-timeline.component';
import { SourceDrawerComponent } from '../../shared/source-drawer.component';
import { currentPolicy, customerEscalationMessage, feedbackReasons, groupByPolicy, policyLabel } from '../../shared/labels';
import { ToastService } from '../../shared/toast';
import { numberedSources } from '../tier1/ticket-workspace.component';

interface AgentTurn {
  steps: Step[];
  result: TicketAnswer | null;
  status: 'running' | 'done' | 'error';
  error: string | null;
  sub?: Subscription;
  report: { open: boolean; reason: string; comment: string; busy: boolean; sent: boolean };
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

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule, StepTimelineComponent, SourceDrawerComponent],
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
  chatMode: 'rag' | 'agent' = 'agent';
  customers: CustomerOption[] = [];
  customerId = '';
  customersFailed = false;
  canChoose = false;
  ownAccount: { customer_id: string; region: string; plan: string; policy_version: PolicyVersion } | null = null;
  accountLoaded = false;
  drawer: { slug: string; text: string } | null = null;
  get reportReasons() { return feedbackReasons(); }
  reasons: FeedbackReason[] = DEFAULT_REASONS;

  constructor(
    private chatService: ChatService,
    private tier1: Tier1Service,
    private toast: ToastService,
  ) {}

  ngOnInit(): void {
    this.loadCustomers();
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
    for (const m of this.messages) m.agentTurn?.sub?.unsubscribe();
  }

  // ------------------------------------------------------------ customer picker

  /** Admins pick any customer; everyone else acts as the account linked to their own sign-in. */
  loadCustomers(): void {
    this.customersFailed = false;
    this.tier1.meCustomer().subscribe({
      next: me => {
        this.accountLoaded = true;
        this.canChoose = me.can_choose;
        this.ownAccount = me.customer;
        if (me.can_choose) this.loadPicker();
      },
      error: () => { this.customersFailed = true; },
    });
  }

  get hasAccount(): boolean { return this.canChoose ? !!this.customerId : !!this.ownAccount; }

  private loadPicker(): void {
    this.tier1.customers().subscribe({
      next: list => {
        this.customers = list;
        if (!this.customerId) {
          this.customerId = (list.find(c => c.policy_version === currentPolicy()) ?? list[0])?.customer_id ?? '';
        }
      },
      error: () => { this.customersFailed = true; },
    });
  }

  get customerGroups() { return groupByPolicy(this.customers); }

  get selectedCustomer(): CustomerOption | undefined {
    return this.customers.find(c => c.customer_id === this.customerId);
  }

  policyText(c: CustomerOption | undefined): string {
    return c ? policyLabel(c.policy_version) : '';
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

  // ------------------------------------------------------------ agent answers (Tier-1 assistant)

  sourceList(turn: AgentTurn): { n: number; slug: string }[] {
    const r = turn.result;
    return r ? numberedSources(r.customer_reply, r.citations) : [];
  }

  openSource(turn: AgentTurn, slug: string): void {
    this.drawer = { slug, text: turn.result?.sources.find(x => x.slug === slug)?.text ?? '' };
  }

  escalationText(r: TicketAnswer): string { return customerEscalationMessage(r.reason); }

  copyReply(text: string): void {
    navigator.clipboard?.writeText(text).then(() => this.toast.success('Reply copied.'));
  }

  openReport(turn: AgentTurn): void {
    turn.report.open = !turn.report.open;
  }

  sendReport(turn: AgentTurn): void {
    const r = turn.report;
    if (!turn.result || r.busy || !r.reason) return;
    r.busy = true;
    this.tier1.sendFeedback({ trace_id: turn.result.trace_id, reason: r.reason, comment: r.comment.trim() || undefined }).subscribe({
      next: () => { r.busy = false; r.sent = true; r.open = false; this.toast.success('Thanks. This was sent to the team for review.'); },
      error: () => { r.busy = false; this.toast.error('Could not send the report. Please try again.'); },
    });
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
    if (!this.hasAccount) {
      this.toast.error(this.canChoose ? 'Choose a customer first.' : 'No customer account is linked to your sign-in.');
      this.inputText = msg;
      return;
    }
    const turn: AgentTurn = {
      steps: [], result: null, status: 'running', error: null,
      report: { open: false, reason: '', comment: '', busy: false, sent: false },
    };
    this.messages.push({ role: 'user', text: msg });
    this.messages.push({ role: 'assistant', text: '', agentTurn: turn });
    this.loading = true;

    this.tier1.answer({ text: msg, customer_id: this.canChoose ? this.customerId : undefined }).subscribe({
      next: ({ job_id }) => {
        turn.sub = this.tier1.pollJob(job_id).subscribe({
          next: j => {
            turn.steps = j.steps;
            if (j.status === 'done' && j.result) { turn.result = j.result; turn.status = 'done'; this.loading = false; }
            if (j.status === 'error') { turn.status = 'error'; turn.error = j.error ?? 'The assistant could not finish.'; this.loading = false; }
          },
          error: () => { turn.status = 'error'; turn.error = 'Lost contact with the server. Please try again.'; this.loading = false; },
        });
      },
      error: e => {
        turn.status = 'error';
        turn.error = e?.status === 429 ? 'The assistant is busy. Try again in a minute.' : 'The assistant could not be started.';
        this.loading = false;
      },
    });
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
