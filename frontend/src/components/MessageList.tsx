import { useEffect, useRef } from 'react';
import type { ChatMessage, LegalSource } from '../types/chat';
import { LoadingIndicator } from './LoadingIndicator';
import { MessageBubble } from './MessageBubble';

interface MessageListProps {
  messages: ChatMessage[];
  isLoading: boolean;
  onSuggestionSelect: (suggestion: string) => void;
  onCitationOpen: (source: LegalSource) => void;
}

const suggestions = [
  'Đầu tư kinh doanh là gì?',
  'Có những hình thức đầu tư kinh doanh nào phổ biến?',
  'Một dự án đầu tư được cấp phép nhưng nhiều năm không triển khai thì cơ quan nhà nước có thể xử lý dự án như thế nào?',
] as const;

const EmptyConversation = ({
  onSuggestionSelect,
}: Pick<MessageListProps, 'onSuggestionSelect'>) => (
  <div className="empty-state">
    <div className="empty-state__copy">
      <h2>Tra cứu pháp luật có căn cứ</h2>
      <p className="empty-state__description">
        Đặt câu hỏi bằng ngôn ngữ tự nhiên. Hệ thống sẽ tìm nguồn, đối chiếu từng
        nhận định và hiển thị rõ phần nào đã có căn cứ pháp lý.
      </p>
    </div>

    <button
      type="button"
      className="rag-preview"
      onClick={() => onSuggestionSelect(suggestions[0])}
      aria-label={`Dùng câu hỏi mẫu: ${suggestions[0]}`}
    >
      <div className="rag-preview__top">
        <span className="rag-preview__status"><i aria-hidden="true" /> Có căn cứ</span>
        <span>Ví dụ cách hệ thống trả lời</span>
      </div>
      <p className="rag-preview__question">“{suggestions[0]}”</p>
      <div className="rag-preview__answer">
        <span className="rag-preview__avatar" aria-hidden="true">AI</span>
        <div>
          <p>Câu trả lời được chia thành nhận định và gắn với nguồn đã đối chiếu.</p>
          <span className="rag-preview__citation">[Điều/Khoản từ văn bản]</span>
        </div>
      </div>
    </button>

    <div className="suggestion-area">
      <h3>Câu hỏi gợi ý</h3>
      <div className="suggestion-list">
        {suggestions.map((suggestion) => (
          <button key={suggestion} type="button" onClick={() => onSuggestionSelect(suggestion)}>
            <svg viewBox="0 0 20 20" aria-hidden="true" className="suggestion-list__question-icon">
              <path d="M10 15.5h.01M7.8 7.6a2.4 2.4 0 1 1 3.4 2.2c-.8.4-1.2.9-1.2 1.7" />
            </svg>
            {suggestion}
            <svg viewBox="0 0 20 20" aria-hidden="true">
              <path d="M4 10h12m-4-4 4 4-4 4" />
            </svg>
          </button>
        ))}
      </div>
    </div>
  </div>
);

export const MessageList = ({
  messages,
  isLoading,
  onSuggestionSelect,
  onCitationOpen,
}: MessageListProps) => {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, isLoading]);

  return (
    <section className="message-list" aria-label="Lịch sử hội thoại" aria-live="polite">
      <div className="message-list__inner">
        {messages.length === 0 ? (
          <EmptyConversation onSuggestionSelect={onSuggestionSelect} />
        ) : (
          messages.map((message) => (
            <MessageBubble
              key={message.id}
              message={message}
              onCitationOpen={onCitationOpen}
            />
          ))
        )}
        {isLoading && <LoadingIndicator />}
        <div ref={endRef} aria-hidden="true" />
      </div>
    </section>
  );
};
