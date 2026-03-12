'use client';

interface UserMessageProps {
  content: string;
}

export default function UserMessage({ content }: UserMessageProps) {
  return (
    <div className="flex justify-end">
      <div className="max-w-2xl bg-blue-600 text-white p-4 rounded-2xl rounded-tr-none shadow-md">
        <p className="text-sm leading-relaxed">{content}</p>
      </div>
    </div>
  );
}
