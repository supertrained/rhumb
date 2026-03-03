import type { Service } from "../lib/types";

/** Display a summarized service card. */
export function ServiceCard({ service }: { service: Service }): JSX.Element {
  return (
    <article style={{ border: "1px solid #e2e8f0", borderRadius: 12, padding: 16 }}>
      <h3>{service.name}</h3>
      <p>{service.description ?? "No description yet."}</p>
      <small>{service.category}</small>
    </article>
  );
}
