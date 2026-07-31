export function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="score-bar">
      <div><span>{label}</span><b>{value.toFixed(0)}</b></div>
      <div className="score-track" aria-label={`${label}: ${value.toFixed(0)} out of 100`} role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={value}>
        <span style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </div>
    </div>
  );
}
