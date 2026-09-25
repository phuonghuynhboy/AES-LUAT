import {
  CHAT_STATUSES,
  type ChatRequest,
  type ChatResponse,
  type ChatStatus,
} from '../types/chat.ts';
import { apiConfig } from '../config/apiConfig.ts';
import { normalizeChatResponse } from './normalizeChatResponse.ts';

const isChatStatus = (value: unknown): value is ChatStatus =>
  typeof value === 'string' && CHAT_STATUSES.some((status) => status === value);

const getMockStatus = (): ChatStatus => {
  const status = import.meta.env.VITE_MOCK_STATUS;
  return isChatStatus(status) ? status : 'full_answer';
};

const createMockResponse = async (request: ChatRequest): Promise<ChatResponse> => {
  await new Promise((resolve) => window.setTimeout(resolve, 900));

  const status = getMockStatus();
  const mockSourceTextEnabled =
    (import.meta.env.VITE_MOCK_SOURCE_TEXT ?? 'true').toLowerCase() === 'true';
  const mockSourceMetadataEnabled =
    (import.meta.env.VITE_MOCK_SOURCE_METADATA ?? 'true').toLowerCase() === 'true';
  const mockClaimText = `Đây là claim mô phỏng cho câu hỏi: “${request.question}”. Nội dung này không phải kết luận pháp lý.`;
  const mockSource = {
    provision_id: 'MOCK#citation-ui.source-1',
    provision_key: 'MOCK#logical-source-1',
    breadcrumb: 'Nguồn mô phỏng > Điều thử nghiệm > Khoản thử nghiệm',
    doc_id: 'MOCK-DOC',
    text: mockSourceTextEnabled
      ? 'Nội dung nguồn mô phỏng để kiểm thử Citation Panel. Đây không phải quy định pháp luật.'
      : undefined,
    valid_from: null,
    valid_to: null,
    temporal_warning: null,
  };
  const answers: Record<ChatStatus, string> = {
    full_answer: mockClaimText,
    partial_answer:
      `${mockClaimText}\nMột phần khác của câu hỏi chưa có đủ căn cứ trong dữ liệu mô phỏng.`,
    refusal:
      'Đây là phản hồi từ chối mô phỏng. Backend thật chưa được kết nối để xác định căn cứ pháp lý.',
  };

  return {
    status,
    answer: answers[status],
    claims:
      status === 'refusal'
        ? []
        : [
            {
              claim_id: 'mock_claim_1',
              text: mockClaimText,
              answerable: true,
              evidence_chunk_ids: [mockSource.provision_id],
              status: 'supported',
            },
            ...(status === 'partial_answer'
              ? [
                  {
                    claim_id: 'mock_claim_2',
                    question_part: 'Một phần khác của câu hỏi (mô phỏng)',
                    text: 'Phần chưa được hỗ trợ trong dữ liệu mô phỏng.',
                    answerable: false,
                    evidence_chunk_ids: [],
                    status: 'unsupported' as const,
                  },
                ]
              : []),
          ],
    sources:
      status !== 'refusal' && mockSourceMetadataEnabled ? [mockSource] : [],
    // Retrieval candidates are audit metadata and are never rendered as citations.
    retrieved_sources: mockSourceMetadataEnabled ? [mockSource] : [],
    warnings: [],
  };
};

export class ChatServiceError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ChatServiceError';
  }
}

interface ChatRequesterOptions {
  fetchImpl?: typeof fetch;
  chatUrl?: string;
  timeoutMs?: number;
  useMock?: boolean;
}

export const createChatRequester = ({
  fetchImpl = globalThis.fetch.bind(globalThis),
  chatUrl = apiConfig.chatUrl,
  timeoutMs = apiConfig.requestTimeoutMs,
  useMock = apiConfig.useMock,
}: ChatRequesterOptions = {}) => async (question: string): Promise<ChatResponse> => {
  const request: ChatRequest = { question: question.trim() };

  if (!request.question) {
    throw new ChatServiceError('Vui lòng nhập câu hỏi trước khi gửi.');
  }

  if (useMock) {
    return createMockResponse(request);
  }

  const controller = new AbortController();
  const timeoutId = globalThis.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetchImpl(chatUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new ChatServiceError(
        response.status >= 500
          ? 'Máy chủ đang gặp sự cố. Vui lòng thử lại sau.'
          : 'Yêu cầu chưa được xử lý. Vui lòng kiểm tra câu hỏi và thử lại.',
      );
    }

    try {
      return normalizeChatResponse(await response.json());
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') throw error;
      throw new ChatServiceError(
        'Máy chủ trả về dữ liệu chưa đúng định dạng. Vui lòng thử lại sau.',
      );
    }
  } catch (error) {
    if (error instanceof ChatServiceError) {
      throw error;
    }

    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ChatServiceError('Yêu cầu mất quá nhiều thời gian. Vui lòng thử lại.');
    }

    throw new ChatServiceError(
      'Không thể kết nối tới hệ thống xử lý pháp lý. Vui lòng thử lại.',
    );
  } finally {
    globalThis.clearTimeout(timeoutId);
  }
};

export const sendChatMessage = createChatRequester();

export const chatServiceConfig = {
  apiUrl: apiConfig.chatUrl,
  useMock: apiConfig.useMock,
} as const;
