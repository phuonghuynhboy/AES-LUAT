import type { ChatMessage } from '../types/chat';
import type { LegalSource } from '../types/chat';
import { chatServiceConfig } from '../services/chatService';
import { ClaimRenderer } from './ClaimRenderer';

interface MessageBubbleProps {
  message: ChatMessage;
  onCitationOpen: (source: LegalSource) => void;
}

const formatTime = (timestamp: string) =>
  new Intl.DateTimeFormat('vi-VN', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(timestamp));

const warningLabels: Record<string, string> = {
  INSUFFICIENT_LEGAL_EVIDENCE: 'Hệ thống chưa tìm thấy đủ căn cứ pháp lý để trả lời.',
  PARTIAL_ANSWER_SOME_CLAIMS_NOT_FULLY_SUPPORTED:
    'Một phần câu hỏi chưa có đủ căn cứ trong nguồn hiện có.',
};

const formatWarning = (warning: string) => warningLabels[warning] ?? warning;

const getStatusMeta = (message: ChatMessage) => {
  if (message.isError) return { label: 'Kết nối gián đoạn', tone: 'error' };
  if (message.status === 'partial_answer') return { label: 'Thông tin một phần', tone: 'partial' };
  if (message.status === 'refusal') return { label: 'Chưa đủ căn cứ', tone: 'refusal' };
  return { label: 'Đã tổng hợp', tone: 'full' };
};

const StatusNotice = ({ message }: Pick<MessageBubbleProps, 'message'>) => {
  if (message.status === 'partial_answer') {
    return (
      <div className="status-notice status-notice--partial">
        Một phần câu hỏi chưa có đủ căn cứ để kết luận.
      </div>
    );
  }

  if (message.status === 'refusal') {
    return (
      <div className="status-notice status-notice--refusal">
        Hệ thống chưa có đủ căn cứ pháp lý để trả lời câu hỏi này.
      </div>
    );
  }

  return null;
};

export const MessageBubble = ({ message, onCitationOpen }: MessageBubbleProps) => {
  if (message.role === 'user') {
    return (
      <article className="message-row message-row--user">
        <div className="message-content message-content--user">
          <div className="message-bubble message-bubble--user">
            <p>{message.content}</p>
          </div>
          <time className="message-time" dateTime={message.timestamp}>
            Bạn · {formatTime(message.timestamp)}
          </time>
        </div>
      </article>
    );
  }

  const statusMeta = getStatusMeta(message);

  return (
    <article className="message-row message-row--assistant">
      <div className={`assistant-card${message.isError ? ' assistant-card--error' : ''}`}>
        <div className="assistant-card__header">
          <div className="assistant-identity">
            <div className="message-avatar" aria-hidden="true">AES</div>
            <div>
              <strong>AES LUẬT</strong>
              <time dateTime={message.timestamp}>{formatTime(message.timestamp)}</time>
            </div>
          </div>
          <div className="assistant-card__badges">
            {chatServiceConfig.useMock && <span className="mock-badge">Mô phỏng</span>}
            <span className={`answer-status answer-status--${statusMeta.tone}`}>
              <i aria-hidden="true" />
              {statusMeta.label}
            </span>
          </div>
        </div>

        <div className="assistant-card__body">
          <StatusNotice message={message} />
          <ClaimRenderer message={message} onCitationOpen={onCitationOpen} />

          {message.warnings && message.warnings.length > 0 && (
            <ul className="message-warnings" aria-label="Lưu ý từ hệ thống">
              {message.warnings.map((warning, index) => (
                <li key={`${message.id}-warning-${index}`}>{formatWarning(warning)}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </article>
  );
};
