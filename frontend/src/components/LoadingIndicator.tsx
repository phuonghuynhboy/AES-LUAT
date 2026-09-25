import { chatServiceConfig } from '../services/chatService';

export const LoadingIndicator = () => (
  <div className="message-row message-row--assistant" aria-live="polite" aria-label="Trợ lý đang xử lý">
    <div className="assistant-card assistant-card--loading">
      <div className="assistant-card__header">
        <div className="assistant-identity">
          <div className="message-avatar" aria-hidden="true">AES</div>
          <div>
            <strong>AES LUẬT</strong>
            <span>Đang làm việc</span>
          </div>
        </div>
        <span className="loading-dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
      </div>
      <div className="loading-card">
        <p>
          {chatServiceConfig.useMock
            ? 'Đang chuẩn bị phản hồi mô phỏng'
            : 'Đang chờ hệ thống xử lý và tổng hợp câu trả lời'}
        </p>
        <div className="loading-lines" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
      </div>
    </div>
  </div>
);
