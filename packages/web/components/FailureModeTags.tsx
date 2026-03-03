/** Tag list for failure mode categories. */
export function FailureModeTags({ tags }: { tags: string[] }): JSX.Element {
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      {tags.map((tag) => (
        <span key={tag} style={{ padding: "2px 8px", border: "1px solid #cbd5e1", borderRadius: 8 }}>
          {tag}
        </span>
      ))}
    </div>
  );
}
