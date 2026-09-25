import { chatServiceConfig } from '../services/chatService';
import type { ChatMessage } from '../types/chat';

interface ConversationSidebarProps {
  messages: ChatMessage[];
  isLoading: boolean;
  onNewConversation: () => void;
  onQuestionSelect: (question: string) => void;
}

export const ConversationSidebar = ({
  messages,
  isLoading,
  onNewConversation,
  onQuestionSelect,
}: ConversationSidebarProps) => {
  const recentQuestions = messages
    .filter((message) => message.role === 'user')
    .slice(-6)
    .reverse();

  return (
    <aside className="legal-rail" aria-label="Điều hướng hội thoại">
      <div className="rail-main">
        <div className="rail-brand">
          <div className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" fill="none">
              <path d="M16 4v22M7 10h18M9 10 5.5 18h7L9 10Zm14 0-3.5 8h7L23 10ZM10.5 27h11" />
            </svg>
          </div>
          <div>
            <div className="rail-brand__name">AES <span>LUẬT</span></div>
            <p>Trợ lý tra cứu pháp luật</p>
          </div>
        </div>

        <button
          type="button"
          className="new-conversation-button"
          onClick={onNewConversation}
          disabled={isLoading}
        >
          <svg viewBox="0 0 20 20" aria-hidden="true">
            <path d="M10 4v12M4 10h12" />
          </svg>
          Cuộc trò chuyện mới
        </button>

        <nav className="recent-questions" aria-label="Câu hỏi gần đây">
          <h2>Câu hỏi gần đây</h2>
          {recentQuestions.length === 0 ? (
            <p className="recent-questions__empty">
              Câu hỏi bạn gửi trong phiên này sẽ xuất hiện tại đây.
            </p>
          ) : (
            <ul>
              {recentQuestions.map((message) => (
                <li key={message.id}>
                  <button
                    type="button"
                    onClick={() => onQuestionSelect(message.content)}
                    title={message.content}
                  >
                    <svg viewBox="0 0 20 20" aria-hidden="true">
                      <path d="M4 5.5h12M4 10h8M4 14.5h10" />
                    </svg>
                    <span>{message.content}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </nav>
      </div>

      <div className="rail-footer">
        <div
          className={`rail-status${chatServiceConfig.useMock ? ' rail-status--mock' : ''}`}
          title={chatServiceConfig.useMock ? 'Đang dùng dữ liệu mô phỏng' : chatServiceConfig.apiUrl}
        >
          <span aria-hidden="true" />
          {chatServiceConfig.useMock ? 'Dữ liệu mô phỏng' : 'API đã cấu hình'}
        </div>
      </div>
    </aside>
  );
};
