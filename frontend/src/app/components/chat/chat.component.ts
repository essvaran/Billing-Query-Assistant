import {
  Component,
  ElementRef,
  ViewChild,
  AfterViewChecked,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClientModule } from '@angular/common/http';
import { ChatService, Message, AskResponse } from '../../services/chat.service';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule],
  templateUrl: './chat.component.html',
  styleUrl: './chat.component.scss',
})
export class ChatComponent implements AfterViewChecked {
  @ViewChild('messagesEnd') private messagesEnd!: ElementRef;

  messages: Message[] = [];
  inputText = '';
  loading = false;
  expandedChunks: Set<number> = new Set();

  constructor(private chatService: ChatService) {}

  ngAfterViewChecked(): void {
    this.scrollToBottom();
  }

  sendMessage(): void {
    const question = this.inputText.trim();
    if (!question || this.loading) return;

    this.messages.push({ role: 'user', text: question });
    this.inputText = '';
    this.loading = true;

    this.chatService.ask(question).subscribe({
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

  private scrollToBottom(): void {
    try {
      this.messagesEnd.nativeElement.scrollIntoView({ behavior: 'smooth' });
    } catch {}
  }
}
