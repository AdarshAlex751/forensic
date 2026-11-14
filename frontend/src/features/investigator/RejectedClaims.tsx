import "./investigator.css";

export interface RejectedClaim {
  claim: string;
  reason: string;
}

export interface RejectedClaimsProps {
  rejected: RejectedClaim[];
  /** Optional id so a toggle button can point at the list via aria-controls. */
  id?: string;
}

const CUSTODY_PREFIX = /^custody:\s*/i;

/**
 * What the verifier threw out and why. A "custody:" reason means the source
 * failed a chain-of-custody check, so the claim is not trusted; it is not
 * shown as false.
 */
export function RejectedClaims({ rejected, id }: RejectedClaimsProps) {
  if (rejected.length === 0) {
    return (
      <p id={id} className="inv-state inv-plain">
        The verifier rejected nothing. Every claim matched its cited source line.
      </p>
    );
  }

  return (
    <ul id={id} className="inv-rejected" aria-label="Rejected claims">
      {rejected.map((r, i) => {
        const custody = CUSTODY_PREFIX.test(r.reason);
        const reason = custody ? r.reason.replace(CUSTODY_PREFIX, "") : r.reason;
        return (
          <li key={`${i}-${r.claim}`} className={custody ? "inv-is-custody" : undefined}>
            <span className={custody ? "inv-claim" : "inv-claim inv-claim-struck"}>{r.claim}</span>
            <span className="inv-reason">
              {custody ? (
                <span className="inv-tag inv-tag-ochre">Not trusted: custody</span>
              ) : (
                <span className="inv-tag inv-tag-red">Rejected</span>
              )}
              <span>{reason}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}
