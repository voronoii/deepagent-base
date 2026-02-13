'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { ChatMessage, ReasoningStep, AssistantMessageData, TokenUsage } from '@/types';
import { sendMessage } from '@/lib/api';
import Sidebar from '@/components/Sidebar';
import ChatArea from '@/components/ChatArea';
import ReasoningPanel from '@/components/ReasoningPanel';

function generateId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function updateStepsList(prev: ReasoningStep[], step: ReasoningStep): ReasoningStep[] {
  const existingIdx = prev.findIndex((s) => s.name === step.name);
  if (existingIdx >= 0) {
    const updated = [...prev];
    updated[existingIdx] = step;
    return updated;
  }
  return [...prev, step];
}

export default function Home() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [reasoningSteps, setReasoningSteps] = useState<ReasoningStep[]>([]);
  const [liveReasoningSteps, setLiveReasoningSteps] = useState<ReasoningStep[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [tokenUsage, setTokenUsage] = useState<TokenUsage | null>(null);
  const threadIdRef = useRef<string>('');
  const currentStepsRef = useRef<ReasoningStep[]>([]);

  useEffect(() => {
    threadIdRef.current = generateId();
  }, []);

  const handleSend = useCallback(async (content: string) => {
    if (isLoading) return;

    const userMessage: ChatMessage = {
      id: generateId(),
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setReasoningSteps([]);
    setLiveReasoningSteps([]);
    currentStepsRef.current = [];
    setIsLoading(true);

    await sendMessage(content, threadIdRef.current, {
      onReasoningStep: (step: ReasoningStep) => {
        // Accumulate in ref for attaching to final message
        currentStepsRef.current = updateStepsList(currentStepsRef.current, step);

        // Update live display for the in-progress loading area
        setLiveReasoningSteps((prev) => updateStepsList(prev, step));

        // Keep the right panel in sync
        setReasoningSteps((prev) => updateStepsList(prev, step));
      },
      onMetadata: (data: TokenUsage) => {
        setTokenUsage(data);
      },
      onMessage: (data: AssistantMessageData) => {
        // Attach accumulated reasoning steps to the assistant message
        const assistantMessage: ChatMessage = {
          id: generateId(),
          role: 'assistant',
          content: data.content,
          assistantData: data,
          reasoningSteps: currentStepsRef.current.length > 0
            ? [...currentStepsRef.current]
            : undefined,
          timestamp: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, assistantMessage]);

        // Clear live steps since they are now embedded in the message
        setLiveReasoningSteps([]);
        currentStepsRef.current = [];
      },
      onDone: () => {
        setIsLoading(false);
      },
      onError: (error: Error) => {
        console.error('Chat error:', error);
        const errorMessage: ChatMessage = {
          id: generateId(),
          role: 'assistant',
          content: 'An error occurred while processing your request. Please try again.',
          assistantData: {
            content: 'An error occurred while processing your request. Please try again.',
            title: 'Error',
          },
          reasoningSteps: currentStepsRef.current.length > 0
            ? [...currentStepsRef.current]
            : undefined,
          timestamp: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, errorMessage]);
        setLiveReasoningSteps([]);
        currentStepsRef.current = [];
        setIsLoading(false);
      },
    });
  }, [isLoading]);

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <ChatArea
        messages={messages}
        isLoading={isLoading}
        liveReasoningSteps={liveReasoningSteps}
        onSend={handleSend}
        tokenUsage={tokenUsage}
      />
      <ReasoningPanel
        steps={reasoningSteps}
        isActive={isLoading}
      />
    </div>
  );
}
