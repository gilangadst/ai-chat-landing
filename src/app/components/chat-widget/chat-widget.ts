import { Component, ElementRef, ViewChild, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import { ChatHistoryItem, ChatMessage } from '../../models/chat';
import { ChatService } from '../../services/chat.service';

@Component({
  selector: 'app-chat-widget',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './chat-widget.html',
  styleUrl: './chat-widget.css',
})
export class ChatWidgetComponent {
  private readonly chat = inject(ChatService);

  @ViewChild('thread') thread?: ElementRef<HTMLDivElement>;

  readonly open = signal(false);
  readonly pending = signal(false);
  readonly draft = signal('');
  readonly messages = signal<ChatMessage[]>([
    {
      role: 'assistant',
      text: 'Halo. Saya asisten kebudayaan Indonesia. Tanyakan tarian, upacara, kuliner, atau warisan budaya Nusantara.',
    },
  ]);

  toggle(): void {
    this.open.update((value) => !value);
  }

  send(): void {
    const text = this.draft().trim();
    if (!text || this.pending()) {
      return;
    }

    const history = this.toHistory(this.messages());
    this.messages.update((items) => [...items, { role: 'user', text }]);
    this.draft.set('');
    this.pending.set(true);
    this.scrollSoon();

    this.chat
      .send(text, history)
      .pipe(finalize(() => this.pending.set(false)))
      .subscribe({
        next: (res) => {
          this.messages.update((items) => [
            ...items,
            { role: 'assistant', text: res.reply },
          ]);
          this.scrollSoon();
        },
        error: (error: unknown) => {
          const detail =
            error instanceof HttpErrorResponse &&
            typeof error.error?.detail === 'string'
              ? error.error.detail
              : 'Backend belum merespons. Jalankan `python backend/main.py`, pastikan file CSV dan joblib ada di folder backend, lalu coba lagi.';
          this.messages.update((items) => [
            ...items,
            {
              role: 'assistant',
              text: detail,
            },
          ]);
          this.scrollSoon();
        },
      });
  }

  private toHistory(messages: ChatMessage[]): ChatHistoryItem[] {
    const history: ChatHistoryItem[] = [];
    const start = messages[0]?.role === 'assistant' ? 1 : 0;

    for (let i = start; i < messages.length - 1; i += 2) {
      const user = messages[i];
      const bot = messages[i + 1];
      if (user?.role === 'user' && bot?.role === 'assistant') {
        history.push({ user: user.text, bot: bot.text });
      }
    }

    return history;
  }

  private scrollSoon(): void {
    queueMicrotask(() => {
      const el = this.thread?.nativeElement;
      if (el) {
        el.scrollTop = el.scrollHeight;
      }
    });
  }
}
