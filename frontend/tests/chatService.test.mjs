import assert from 'node:assert/strict';
import test from 'node:test';
import { ChatServiceError, createChatRequester } from '../src/services/chatService.ts';

const validPayload = {
  status: 'full_answer',
  answer: 'Answer',
  claims: [],
  sources: [],
  retrieved_sources: [],
  warnings: [],
};

test('real API requester posts the trimmed question to its single configured endpoint', async () => {
  let captured;
  const requester = createChatRequester({
    chatUrl: 'http://api.test/api/chat',
    useMock: false,
    fetchImpl: async (url, init) => {
      captured = { url, init };
      return Response.json(validPayload);
    },
  });

  const response = await requester('  Question  ');

  assert.equal(response.status, 'full_answer');
  assert.equal(captured.url, 'http://api.test/api/chat');
  assert.equal(captured.init.method, 'POST');
  assert.deepEqual(JSON.parse(captured.init.body), { question: 'Question' });
});

test('offline backend surfaces a friendly error and never falls back to mock', async () => {
  let calls = 0;
  const requester = createChatRequester({
    useMock: false,
    fetchImpl: async () => {
      calls += 1;
      throw new TypeError('network offline');
    },
  });

  await assert.rejects(
    requester('Question'),
    (error) =>
      error instanceof ChatServiceError &&
      error.message === 'Không thể kết nối tới hệ thống xử lý pháp lý. Vui lòng thử lại.',
  );
  assert.equal(calls, 1);
});

test('HTTP 500 and malformed JSON responses are explicit errors', async () => {
  const serverError = createChatRequester({
    useMock: false,
    fetchImpl: async () => new Response('', { status: 500 }),
  });
  const malformed = createChatRequester({
    useMock: false,
    fetchImpl: async () => Response.json({ status: 'full_answer' }),
  });

  await assert.rejects(serverError('Question'), /Máy chủ đang gặp sự cố/);
  await assert.rejects(malformed('Question'), /dữ liệu chưa đúng định dạng/);
});

test('timeout aborts the request and returns a friendly timeout error', async () => {
  const requester = createChatRequester({
    useMock: false,
    timeoutMs: 5,
    fetchImpl: async (_url, init) =>
      new Promise((_resolve, reject) => {
        init.signal.addEventListener('abort', () => {
          reject(new DOMException('Aborted', 'AbortError'));
        });
      }),
  });

  await assert.rejects(requester('Question'), /mất quá nhiều thời gian/);
});

test('empty questions are rejected before any HTTP request', async () => {
  let called = false;
  const requester = createChatRequester({
    useMock: false,
    fetchImpl: async () => {
      called = true;
      return Response.json(validPayload);
    },
  });

  await assert.rejects(requester('   '), /Vui lòng nhập câu hỏi/);
  assert.equal(called, false);
});
