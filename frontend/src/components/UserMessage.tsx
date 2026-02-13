'use client';

interface UserMessageProps {
  content: string;
}

export default function UserMessage({ content }: UserMessageProps) {
  return (
    <div className="flex justify-end">
      <div className="max-w-2xl bg-primary text-white p-4 rounded-2xl rounded-tr-none shadow-sm">
        <p className="text-sm leading-relaxed">{content}</p>
      </div>
    </div>
  );
}
