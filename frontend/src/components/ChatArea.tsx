'use client';

import { useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChatMessage, ReasoningStep, TokenUsage } from '@/types';
import UserMessage from './UserMessage';
import AssistantMessage from './AssistantMessage';
import CollapsibleSteps from './CollapsibleSteps';
import ChatInput from './ChatInput';
import TopNav from './TopNav';

interface ChatAreaProps {
  messages: ChatMessage[];
  isLoading: boolean;
  liveReasoningSteps: ReasoningStep[];
  streamingText: string;
  onSend: (message: string) => void;
  tokenUsage: TokenUsage | null;
}

export default function ChatArea({ messages, isLoading, liveReasoningSteps, streamingText, onSend, tokenUsage }: ChatAreaProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, liveReasoningSteps, streamingText]);

  return (
    <main className="flex-1 flex flex-col relative overflow-hidden bg-slate-50">
      <TopNav />

      {/* Message list */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-8 space-y-8 pb-32">
        {messages.length === 0 && !isLoading && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <span className="material-symbols-outlined text-6xl text-slate-300 mb-4">
              account_balance
            </span>
            <h2 className="text-xl font-semibold text-slate-600 mb-2">
              Welcome to DeepAgents
            </h2>
            <p className="text-sm text-slate-400 max-w-md">
              Ask questions about institutional records, budgets, policies, and more.
              Your AI agent will analyze data and provide verified insights.
            </p>
          </div>
        )}

        {messages.map((msg) => {
          if (msg.role === 'user') {
            return <UserMessage key={msg.id} content={msg.content} />;
          }
          if (msg.role === 'assistant' && msg.assistantData) {
            return (
              <AssistantMessage
                key={msg.id}
                data={msg.assistantData}
                reasoningSteps={msg.reasoningSteps}
              />
            );
          }
          return null;
        })}

        {/* Live reasoning steps while loading */}
        {isLoading && (
          <div className="flex justify-start">
            <div className="max-w-[62rem] flex gap-4">
              <div className="size-8 rounded-lg bg-blue-50 flex items-center justify-center shrink-0 border border-blue-100">
                <span className="material-symbols-outlined text-primary text-lg">smart_toy</span>
              </div>
              <div className="space-y-4 min-w-0 flex-1">
                {liveReasoningSteps.length > 0 && (
                  <CollapsibleSteps steps={liveReasoningSteps} isActive />
                )}
                <div className="bg-white border border-slate-200 p-5 rounded-2xl rounded-tl-none shadow-sm">
                  {streamingText ? (
                    <div className="prose prose-sm max-w-none prose-headings:text-slate-900 prose-headings:font-semibold prose-headings:mt-4 prose-headings:mb-2 prose-p:text-slate-600 prose-p:leading-relaxed prose-p:my-2 prose-strong:text-slate-900 prose-ul:text-slate-600 prose-ol:text-slate-600 prose-li:my-0.5 prose-a:text-blue-600 prose-code:text-blue-600 prose-code:bg-slate-100 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:before:content-none prose-code:after:content-none">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingText}</ReactMarkdown>
                      <span className="inline-block w-2 h-4 bg-primary/60 animate-pulse ml-0.5 align-text-bottom rounded-sm" />
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <div className="flex gap-1">
                        <span className="size-2 bg-primary rounded-full animate-bounce" />
                        <span className="size-2 bg-primary rounded-full animate-bounce [animation-delay:0.2s]" />
                        <span className="size-2 bg-primary rounded-full animate-bounce [animation-delay:0.4s]" />
                      </div>
                      <span className="text-xs text-slate-400 ml-2">Processing your query...</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Input area */}
      <ChatInput onSend={onSend} disabled={isLoading} tokenUsage={tokenUsage} />
    </main>
  );
}
