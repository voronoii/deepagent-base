export interface ReasoningStep {
  name: string;
  status: 'completed' | 'in_progress' | 'pending' | 'error';
  description?: string;
  codeBlock?: string;
  timestamp?: string;
  result?: string;
}

export interface DataCard {
  label: string;
  value: string;
}

export interface Source {
  title: string;
  section: string;
  domain: string;
  similarity: string;
  preview: string;
}

export interface AssistantMessageData {
  content: string;
  title?: string;
  dataCards?: DataCard[];
  sources?: Source[];
  source?: string;
  processingTime?: string;
}

export interface TokenUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  maxContextTokens: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  assistantData?: AssistantMessageData;
  reasoningSteps?: ReasoningStep[];
  timestamp: string;
}
