const viteEnv = import.meta.env ?? ({} as ImportMetaEnv);
const apiBaseUrl = (viteEnv.VITE_API_BASE_URL ?? '').trim().replace(/\/$/, '');
const mockRequested = (viteEnv.VITE_USE_MOCK ?? 'false').toLowerCase() === 'true';
const configuredTimeout = Number(viteEnv.VITE_CHAT_TIMEOUT_MS);

export const apiConfig = {
  chatUrl: `${apiBaseUrl}/api/chat`,
  // A production bundle never serves legal answers from development fixtures.
  useMock: viteEnv.DEV === true && mockRequested,
  requestTimeoutMs:
    Number.isFinite(configuredTimeout) && configuredTimeout > 0
      ? configuredTimeout
      : 120_000,
} as const;
