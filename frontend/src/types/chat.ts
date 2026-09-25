export const CHAT_STATUSES = [
  'full_answer',
  'partial_answer',
  'refusal',
] as const;

export type ChatStatus = (typeof CHAT_STATUSES)[number];

export interface ChatRequest {
  question: string;
}

export type ClaimStatus = 'supported' | 'partially_supported' | 'unsupported';

export interface LegalClaim {
  claim_id: string;
  question_part?: string;
  text: string;
  answerable?: boolean;
  evidence_chunk_ids: string[];
  status?: ClaimStatus;
  score?: number;
  reason?: string;
}

export interface LegalSource {
  provision_id: string;
  provision_key?: string;
  breadcrumb?: string;
  doc_id?: string;
  text?: string;
  valid_from?: string | null;
  valid_to?: string | null;
  temporal_warning?: string | null;
  rrf_score?: number;
  retriever_sources?: string[];
}

export interface ChatResponse {
  status: ChatStatus;
  answer: string;
  claims: LegalClaim[];
  sources: LegalSource[];
  retrieved_sources: LegalSource[];
  warnings: string[];
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  status?: ChatStatus;
  claims?: LegalClaim[];
  sources?: LegalSource[];
  warnings?: string[];
  isError?: boolean;
}
