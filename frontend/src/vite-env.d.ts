/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_USE_MOCK?: string;
  readonly VITE_MOCK_STATUS?: string;
  readonly VITE_MOCK_SOURCE_TEXT?: string;
  readonly VITE_MOCK_SOURCE_METADATA?: string;
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_CHAT_TIMEOUT_MS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
