export interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
}

export interface ChatHistoryItem {
  user: string;
  bot: string;
}

export interface ChatRequest {
  message: string;
  history: ChatHistoryItem[];
}

export interface ChatResponse {
  reply: string;
}
