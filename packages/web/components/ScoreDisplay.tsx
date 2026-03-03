/** Display AN Score summary. */
export function ScoreDisplay({ score }: { score: number | null }): JSX.Element {
  return <p>AN Score: {score ?? "Pending"}</p>;
}
