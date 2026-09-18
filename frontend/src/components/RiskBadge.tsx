export default function RiskBadge({ score }: { score: number | null }) {
  if (score === null)
    return <span className="risk-badge unscored">Unscored</span>;
  const level = score >= 0.7 ? "high" : score >= 0.4 ? "moderate" : "low";
  return (
    <span className={`risk-badge ${level}`}>
      {level} · {score.toFixed(2)}
    </span>
  );
}
