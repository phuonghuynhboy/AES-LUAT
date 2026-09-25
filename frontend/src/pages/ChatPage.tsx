import { useCallback, useRef, useState } from 'react';
import { ChatInput } from '../components/ChatInput';
import { CitationPanel } from '../components/CitationPanel';
import { ConversationSidebar } from '../components/ConversationSidebar';
import { MessageList } from '../components/MessageList';
import {
  ChatServiceError,
  sendChatMessage,
} from '../services/chatService';
import type { ChatMessage, LegalSource } from '../types/chat';

const createMessageId = () =>
  typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

export const ChatPage = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [selectedSource, setSelectedSource] = useState<LegalSource | null>(null);
  const requestInFlightRef = useRef(false);
  const closeCitation = useCallback(() => setSelectedSource(null), []);

  const handleNewConversation = () => {
    if (isLoading) return;
    setMessages([]);
    setDraft('');
    setSelectedSource(null);
  };

  const handleSend = async () => {
    const question = draft.trim();
    if (!question || requestInFlightRef.current) return;

    requestInFlightRef.current = true;

    setMessages((current) => [
      ...current,
      {
        id: createMessageId(),
        role: 'user',
        content: question,
        timestamp: new Date().toISOString(),
      },
    ]);
    setDraft('');
    setIsLoading(true);

    try {
      const response = await sendChatMessage(question);
      setMessages((current) => [
        ...current,
        {
          id: createMessageId(),
          role: 'assistant',
          content:
            response.answer.trim() ||
            (response.status === 'refusal'
              ? 'Hệ thống chưa có đủ căn cứ pháp lý để trả lời câu hỏi này.'
              : 'Hệ thống chưa trả về nội dung trả lời.'),
          timestamp: new Date().toISOString(),
          status: response.status,
          claims: response.claims,
          sources: response.sources,
          warnings: response.warnings,
        },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: createMessageId(),
          role: 'assistant',
          content:
            error instanceof ChatServiceError
              ? error.message
              : 'Đã xảy ra lỗi ngoài dự kiến. Vui lòng thử lại.',
          timestamp: new Date().toISOString(),
          isError: true,
        },
      ]);
    } finally {
      requestInFlightRef.current = false;
      setIsLoading(false);
    }
  };

  return (
    <main className="app-shell">
      <ConversationSidebar
        messages={messages}
        isLoading={isLoading}
        onNewConversation={handleNewConversation}
        onQuestionSelect={setDraft}
      />

      <section className="chat-workspace">
        <header className="workspace-header">
          <div className="mobile-brand" aria-hidden="true">AES</div>
          <h1>Trợ lý tra cứu pháp luật</h1>
        </header>

        <MessageList
          messages={messages}
          isLoading={isLoading}
          onSuggestionSelect={setDraft}
          onCitationOpen={setSelectedSource}
        />

        <footer className="composer-area">
          <ChatInput
            value={draft}
            onChange={setDraft}
            onSend={handleSend}
            isLoading={isLoading}
          />
        </footer>
      </section>
      {selectedSource && (
        <CitationPanel source={selectedSource} onClose={closeCitation} />
      )}
    </main>
  );
};
