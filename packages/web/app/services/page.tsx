import { ServiceCard } from "../../components/ServiceCard";

const MOCK_SERVICES = [
  { slug: "stripe", name: "Stripe", category: "payments", description: "Payments API" },
  { slug: "hubspot", name: "HubSpot", category: "crm", description: "CRM platform" }
];

export default function ServicesPage(): JSX.Element {
  return (
    <section>
      <h1>Services</h1>
      <div style={{ display: "grid", gap: 12 }}>
        {MOCK_SERVICES.map((service) => (
          <ServiceCard key={service.slug} service={service} />
        ))}
      </div>
    </section>
  );
}
