import {
  Component,
  ElementRef,
  ViewChild,
  AfterViewChecked,
} from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClientModule } from '@angular/common/http';
import { ChatService, Message, AskResponse } from '../../services/chat.service';
import { UploadService } from '../../services/upload.service';

interface QuestionItem {
  id: string;
  text: string;
  notInCorpus?: boolean;
}

interface QuestionGroup {
  label: string;
  questions: QuestionItem[];
}

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule, DecimalPipe],
  templateUrl: './chat.component.html',
  styleUrl: './chat.component.scss',
})
export class ChatComponent implements AfterViewChecked {
  @ViewChild('messagesEnd') private messagesEnd!: ElementRef;
  @ViewChild('inputField') private inputField!: ElementRef;

  messages: Message[] = [];
  inputText = '';
  loading = false;
  expandedChunks: Set<number> = new Set();
  hybridMode = true;

  uploadState: 'idle' | 'uploading' | 'success' | 'error' = 'idle';
  uploadMessage = '';
  uploadedFileName = '';

  openGroups: Set<string> = new Set(['Error Codes']);

  questionGroups: QuestionGroup[] = [
    {
      label: 'Error Codes',
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
      questions: [
        { id: 'Q11', text: 'Can I get a refund if my billing migration fails?', notInCorpus: true },
        { id: 'Q12', text: 'What is the processing fee for international credit card payments?', notInCorpus: true },
      ],
    },
  ];

  constructor(private chatService: ChatService, private uploadService: UploadService) {}

  toggleGroup(label: string): void {
    const next = new Set(this.openGroups);
    if (next.has(label)) {
      next.delete(label);
    } else {
      next.add(label);
    }
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

    this.messages.push({ role: 'user', text: question });
    this.inputText = '';
    this.loading = true;

    this.chatService.ask(question, this.hybridMode).subscribe({
      next: (response: AskResponse) => {
        this.messages.push({
          role: 'assistant',
          text: response.answer,
          response,
        });
        this.loading = false;
      },
      error: () => {
        this.messages.push({
          role: 'assistant',
          text: 'Something went wrong. Please try again.',
        });
        this.loading = false;
      },
    });
  }

  toggleChunks(index: number): void {
    if (this.expandedChunks.has(index)) {
      this.expandedChunks.delete(index);
    } else {
      this.expandedChunks.add(index);
    }
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

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (!input.files?.length) return;
    const file = input.files[0];
    input.value = '';

    this.uploadState = 'uploading';
    this.uploadedFileName = file.name;
    this.uploadMessage = '';

    this.uploadService.uploadDocument(file).subscribe({
      next: (res) => {
        this.uploadState = 'success';
        this.uploadMessage = `Indexed ${res.chunks_indexed} chunks`;
        this.messages.push({
          role: 'assistant',
          text: `Document "${res.filename}" uploaded and indexed (${res.chunks_indexed} chunks). You can now ask questions about it.`,
        });
      },
      error: (err) => {
        this.uploadState = 'error';
        this.uploadMessage = err?.error?.detail ?? 'Upload failed';
      },
    });
  }

  resetUpload(): void {
    this.uploadState = 'idle';
    this.uploadMessage = '';
    this.uploadedFileName = '';
  }

  private scrollToBottom(): void {
    try {
      this.messagesEnd.nativeElement.scrollIntoView({ behavior: 'smooth' });
    } catch {}
  }
}
