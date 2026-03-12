import { ReasoningStep, AssistantMessageData, TokenUsage } from '@/types';

interface SendMessageCallbacks {
  onReasoningStep: (step: ReasoningStep) => void;
  onToken?: (content: string) => void;
  onTokenClear?: () => void;
  onMessage: (msg: AssistantMessageData) => void;
  onMetadata?: (data: TokenUsage) => void;
  onDone?: () => void;
  onError?: (error: Error) => void;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

function processSSEEvent(
  event: string,
  data: string,
  callbacks: SendMessageCallbacks
) {
  try {
    const parsed = JSON.parse(data);
    switch (event) {
      case 'reasoning_step':
        callbacks.onReasoningStep(parsed as ReasoningStep);
        break;
      case 'token':
        callbacks.onToken?.(parsed.content as string);
        break;
      case 'token_clear':
        callbacks.onTokenClear?.();
        break;
      case 'message':
        callbacks.onMessage(parsed as AssistantMessageData);
        break;
      case 'metadata':
        callbacks.onMetadata?.(parsed as TokenUsage);
        break;
      case 'done':
        callbacks.onDone?.();
        break;
    }
  } catch {
    // skip malformed JSON
  }
}

export async function sendMessage(
  message: string,
  threadId: string,
  callbacks: SendMessageCallbacks
): Promise<void> {
  try {
    const response = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, thread_id: threadId }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error: ${response.status}`);
    }

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let currentEvent = '';
    let currentData = '';
    let doneEmitted = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.replace(/\r$/, '');
        if (trimmed.startsWith('event: ')) {
          currentEvent = trimmed.slice(7).trim();
        } else if (trimmed.startsWith('data: ')) {
          currentData = trimmed.slice(6);
        } else if (trimmed === '') {
          if (currentEvent && currentData) {
            processSSEEvent(currentEvent, currentData, callbacks);
            if (currentEvent === 'done') doneEmitted = true;
          }
          currentEvent = '';
          currentData = '';
        }
      }
    }

    // Process any remaining event in buffer
    if (currentEvent && currentData) {
      processSSEEvent(currentEvent, currentData, callbacks);
      if (currentEvent === 'done') doneEmitted = true;
    }

    if (!doneEmitted) {
      callbacks.onDone?.();
    }
  } catch (error) {
    callbacks.onError?.(error instanceof Error ? error : new Error(String(error)));
  }
}
