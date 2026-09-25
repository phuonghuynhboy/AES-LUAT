import assert from 'node:assert/strict';
import test from 'node:test';
import {
  buildSourceIndex,
  findSourceByProvisionId,
  formatBackendDate,
  getValidityDisplay,
  getCitableClaims,
  getCitationLabel,
  uniqueEvidenceIds,
} from '../src/utils/citations.ts';
import { normalizeChatResponse } from '../src/services/normalizeChatResponse.ts';

const physicalId = '57-2024-QH15#amd4k3pc.qt6.k4a';
const logicalKey = '22-2023-QH15#d6.k4a';
const source = {
  provision_id: physicalId,
  provision_key: logicalKey,
  breadcrumb: 'Luật Đấu thầu > Điều 6 > Khoản 4a',
  valid_from: '2025-01-15',
  valid_to: null,
};

test('citation matches physical provision_id, never canonical provision_key', () => {
  const sourceIndex = buildSourceIndex([source]);
  assert.equal(findSourceByProvisionId(physicalId, sourceIndex), source);
  assert.equal(findSourceByProvisionId(logicalKey, sourceIndex), undefined);
  assert.equal(findSourceByProvisionId('missing', sourceIndex), undefined);
  assert.equal(getCitationLabel(source), 'Điều 6, Khoản 4a');
  assert.equal(
    getCitationLabel({ ...source, breadcrumb: 'Luật Đấu thầu > Điều 6 > Khoản 4a > Điểm b' }),
    'Điều 6, Khoản 4a, Điểm b',
  );
  assert.equal(getCitationLabel(undefined), 'Nguồn chưa khả dụng');
});

test('source index keeps the first duplicate deterministically', () => {
  const duplicate = { ...source, text: 'second value' };
  const index = buildSourceIndex([{ ...source, text: 'first value' }, duplicate]);

  assert.equal(index.size, 1);
  assert.equal(index.get(physicalId)?.text, 'first value');
});

test('only supported and partially supported claims with evidence are citable', () => {
  const claims = [
    { claim_id: 'a', text: 'A', status: 'supported', evidence_chunk_ids: [physicalId, physicalId] },
    { claim_id: 'b', text: 'B', status: 'partially_supported', evidence_chunk_ids: [physicalId] },
    { claim_id: 'c', text: 'C', status: 'unsupported', evidence_chunk_ids: [physicalId] },
    { claim_id: 'd', text: 'D', status: 'supported', evidence_chunk_ids: [] },
    { claim_id: 'e', text: 'E', status: 'supported', answerable: false, evidence_chunk_ids: [physicalId] },
  ];

  assert.deepEqual(getCitableClaims(claims).map((claim) => claim.claim_id), ['a', 'b']);
  assert.deepEqual(uniqueEvidenceIds(claims[0]), [physicalId]);
});

test('multiple evidence IDs resolve to all corresponding physical sources', () => {
  const secondId = 'SOURCE_B';
  const claim = {
    claim_id: 'multi',
    text: 'Multiple sources',
    status: 'supported',
    evidence_chunk_ids: [physicalId, secondId],
  };
  const index = buildSourceIndex([source, { provision_id: secondId, breadcrumb: 'Điều 2' }]);
  const resolved = uniqueEvidenceIds(claim).map((id) => findSourceByProvisionId(id, index));

  assert.equal(resolved.length, 2);
  assert.deepEqual(resolved.map((item) => item?.provision_id), [physicalId, secondId]);
});

test('backend dates preserve missing, null, malformed and valid values', () => {
  assert.equal(formatBackendDate('2025-01-15'), '15/01/2025');
  assert.equal(formatBackendDate('2026-01-01'), '01/01/2026');
  assert.equal(formatBackendDate(null), 'Chưa ghi nhận');
  assert.equal(formatBackendDate(undefined), 'Backend chưa cung cấp');
  assert.equal(formatBackendDate('2025-02-30'), '2025-02-30');
  assert.deepEqual(
    getValidityDisplay({ provision_id: 'A', valid_from: '2025-01-15', valid_to: '2026-01-01' }),
    { validFrom: '15/01/2025', validTo: '01/01/2026' },
  );
  assert.deepEqual(
    getValidityDisplay({ provision_id: 'A', valid_from: '2025-01-15', valid_to: null }),
    { validFrom: '15/01/2025', validTo: 'Chưa ghi nhận ngày hết hiệu lực' },
  );
});

test('response normalizer preserves source text, dates and verified claim metadata', () => {
  const response = normalizeChatResponse({
    status: 'partial_answer',
    answer: 'Backend answer',
    claims: [
      {
        claim_id: 'claim_1',
        text: 'A claim',
        status: 'supported',
        evidence_chunk_ids: [physicalId],
        score: 0.98,
      },
      { claim_id: 'broken', text: 123, evidence_chunk_ids: [] },
    ],
    sources: [
      { ...source, doc_id: '57-2024-QH15', text: 'Nguồn từ backend', temporal_warning: 'Lưu ý' },
      { provision_id: null },
    ],
    warnings: ['PARTIAL_ANSWER_SOME_CLAIMS_NOT_FULLY_SUPPORTED'],
  });

  assert.equal(response.status, 'partial_answer');
  assert.equal(response.claims.length, 1);
  assert.equal(response.claims[0].evidence_chunk_ids[0], physicalId);
  assert.equal(response.sources.length, 1);
  assert.equal(response.sources[0].text, 'Nguồn từ backend');
  assert.equal(response.sources[0].valid_to, null);
  assert.equal(response.sources[0].temporal_warning, 'Lưu ý');
});

test('response normalizer accepts refusal with retrieved sources but no claims', () => {
  const response = normalizeChatResponse({
    status: 'refusal',
    answer: 'Chưa đủ căn cứ.',
    claims: [],
    sources: [source],
    warnings: [],
  });

  assert.equal(response.status, 'refusal');
  assert.equal(response.claims.length, 0);
  assert.equal(response.sources.length, 1);
});

test('missing source.text remains missing; no legal wording is invented', () => {
  const response = normalizeChatResponse({
    status: 'full_answer',
    answer: 'A',
    claims: [{ claim_id: 'a', text: 'A', status: 'supported', evidence_chunk_ids: [physicalId] }],
    sources: [source],
    warnings: [],
  });

  assert.equal(response.sources[0].text, undefined);
  assert.equal(response.sources[0].valid_to, null);
});
