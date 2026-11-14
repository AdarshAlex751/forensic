import { useFindings } from "../../shared/useFindings";

// Placeholder (Person 1): one row per file with a custody badge.
export function EvidenceLocker() {
  const { data, error, loading } = useFindings();
  if (loading) return <p>Loading evidence...</p>;
  if (error || !data) return <p className="text-red-400">{error}</p>;
  return (
    <div>
      <h2 className="mb-1 text-lg">Evidence locker</h2>
      <ul className="font-mono text-sm">
        {data.evidence.map((e) => (
          <li key={e.file}>
            {e.file} {e.sha256.slice(0, 8)} {e.manifest_match ? "VERIFIED" : "MISMATCH"}
          </li>
        ))}
      </ul>
    </div>
  );
}
