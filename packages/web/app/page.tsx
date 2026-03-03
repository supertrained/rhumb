import Link from "next/link";

export default function HomePage(): JSX.Element {
  return (
    <section>
      <h1>Rhumb</h1>
      <p>Agent-native tool discovery and scoring.</p>
      <Link href="/services">Browse services</Link>
    </section>
  );
}
