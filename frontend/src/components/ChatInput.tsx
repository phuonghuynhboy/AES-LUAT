import { useEffect, useRef, type ChangeEvent, type KeyboardEvent } from 'react';

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  isLoading: boolean;
}

export const ChatInput = ({ value, onChange, onSend, isLoading }: ChatInputProps) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const canSend = value.trim().length > 0 && !isLoading;

  useEffect(() => {
    if (!value && textareaRef.current) textareaRef.current.style.height = 'auto';
  }, [value]);

  const resizeTextarea = (event: ChangeEvent<HTMLTextAreaElement>) => {
    const element = event.currentTarget;
    element.style.height = 'auto';
    element.style.height = `${Math.min(element.scrollHeight, 144)}px`;
    onChange(element.value);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (canSend) onSend();
    }
  };

  return (
    <div className="chat-composer">
      <div className="chat-composer__box">
        <label className="chat-composer__label" htmlFor="legal-question">
          Câu hỏi của bạn
        </label>
        <textarea
          id="legal-question"
          ref={textareaRef}
          rows={1}
          value={value}
          maxLength={10000}
          onChange={resizeTextarea}
          onKeyDown={handleKeyDown}
          placeholder="Mô tả vấn đề pháp lý bạn đang quan tâm..."
          disabled={isLoading}
        />
        <div className="chat-composer__actions">
          <p className="chat-composer__hint">
            <span className="keyboard-key">↵</span> để gửi
            <span className="hint-separator" aria-hidden="true">·</span>
            Shift + Enter để xuống dòng
          </p>
          <button
            type="button"
            className="send-button"
            onClick={onSend}
            disabled={!canSend}
            aria-label={isLoading ? 'Đang chờ phản hồi' : 'Gửi câu hỏi'}
          >
            <span>Gửi</span>
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="m5 12 14-7-4.5 14-3-5.5L5 12Zm6.5 1.5L19 5" />
            </svg>
          </button>
        </div>
      </div>
      <p className="session-note">
        <svg viewBox="0 0 20 20" aria-hidden="true">
          <path d="M6.5 8V6.5a3.5 3.5 0 0 1 7 0V8M5 8h10v8H5V8Z" />
        </svg>
        Nội dung trao đổi chỉ được lưu trong phiên hiện tại
      </p>
      <p className="legal-disclaimer">
        Kết quả chỉ nhằm hỗ trợ tra cứu. Hãy đối chiếu văn bản gốc hoặc tham
        khảo người có chuyên môn trước khi áp dụng.
      </p>
    </div>
  );
};
