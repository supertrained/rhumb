/** Tag list for failure mode categories. */
export function FailureModeTags({ tags }: { tags: string[] }): JSX.Element {
  if (tags.length === 0) {
    return <p className="text-sm text-slate-500 font-mono">No failure modes reported.</p>;
  }

  return (
    <div className="flex flex-wrap gap-2">
      {tags.map((tag) => (
        <span
          key={tag}
          className="px-2.5 py-1 text-xs font-mono rounded-md border border-score-limited/30 bg-score-limited/10 text-score-limited"
        >
          {tag}
        </span>
      ))}
    </div>
  );
}
