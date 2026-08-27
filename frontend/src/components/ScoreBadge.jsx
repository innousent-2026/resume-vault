export default function ScoreBadge({ score }) {
  const band = score >= 70 ? "strong" : score >= 45 ? "maybe" : "weak";
  return (
    <span className={`score ${band}`} title={`Match score ${score} of 100`}>
      {Math.round(score)}
    </span>
  );
}
