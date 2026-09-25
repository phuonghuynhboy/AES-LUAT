import { useMemo } from 'react';
import type { ChatMessage, LegalSource } from '../types/chat';
import {
  buildSourceIndex,
  findSourceByProvisionId,
  getCitableClaims,
  uniqueEvidenceIds,
} from '../utils/citations';
import { CitationBadge } from './CitationBadge';

interface ClaimRendererProps {
  message: ChatMessage;
  onCitationOpen: (source: LegalSource) => void;
}

export const ClaimRenderer = ({ message, onCitationOpen }: ClaimRendererProps) => {
  const claims = message.claims ?? [];
  const sources = message.sources ?? [];
  const sourceIndex = useMemo(() => buildSourceIndex(sources), [sources]);

  // Retrieved candidates không phải citation đã xác minh, đặc biệt khi backend từ chối trả lời.
  if (message.status === 'refusal' || claims.length === 0) {
    return <p className="answer-fallback">{message.content}</p>;
  }

  const citableClaims = getCitableClaims(claims);
  if (citableClaims.length === 0) {
    return (
      <p className="answer-fallback answer-fallback--unverified">
        Chưa có claim đủ metadata citation để hiển thị như kết luận đã xác minh.
      </p>
    );
  }

  const missingParts =
    message.status === 'partial_answer'
      ? claims
          .filter((claim) => claim.status === 'unsupported' && claim.question_part?.trim())
          .map((claim) => claim.question_part!.trim())
      : [];

  return (
    <div className="claim-renderer">
      <div className="claim-list">
        {citableClaims.map((claim) => (
          <div className="claim-item" key={claim.claim_id}>
            <p>
              {claim.text}
              {uniqueEvidenceIds(claim).map((provisionId) => (
                <CitationBadge
                  key={provisionId}
                  provisionId={provisionId}
                  source={findSourceByProvisionId(provisionId, sourceIndex)}
                  onOpen={onCitationOpen}
                />
              ))}
            </p>
            {claim.status === 'partially_supported' && (
              <span className="claim-item__partial">Căn cứ hỗ trợ một phần</span>
            )}
          </div>
        ))}
      </div>

      {missingParts.length > 0 && (
        <div className="unanswered-parts">
          <strong>Phần chưa thể trả lời</strong>
          <ul>
            {[...new Set(missingParts)].map((part) => <li key={part}>{part}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
};
