import type { APIRoute } from "astro";
import { getServices, getCategories } from "../lib/api";

const SITE = "https://rhumb.dev";

// Static pages with their priorities and change frequencies
const STATIC_PAGES = [
  { path: "/", priority: 1.0, changefreq: "daily" },
  { path: "/leaderboard", priority: 0.9, changefreq: "daily" },
  { path: "/about", priority: 0.7, changefreq: "monthly" },
  { path: "/glossary", priority: 0.6, changefreq: "monthly" },
  { path: "/methodology", priority: 0.8, changefreq: "monthly" },
  { path: "/trust", priority: 0.7, changefreq: "monthly" },
  { path: "/providers", priority: 0.7, changefreq: "monthly" },
  { path: "/docs", priority: 0.8, changefreq: "weekly" },
  { path: "/pricing", priority: 0.6, changefreq: "monthly" },
  { path: "/payments/agent", priority: 0.5, changefreq: "monthly" },
  { path: "/search", priority: 0.6, changefreq: "daily" },
  { path: "/compare", priority: 0.8, changefreq: "weekly" },
  { path: "/autopsy", priority: 0.7, changefreq: "weekly" },
  { path: "/quickstart", priority: 0.8, changefreq: "monthly" },
  { path: "/blog", priority: 0.7, changefreq: "weekly" },
  // Comparisons (high SEO value)
  { path: "/blog/stripe-vs-square-vs-paypal", priority: 0.8, changefreq: "monthly" },
  { path: "/blog/resend-vs-sendgrid-vs-postmark", priority: 0.8, changefreq: "monthly" },
  { path: "/blog/hubspot-vs-salesforce-vs-pipedrive", priority: 0.8, changefreq: "monthly" },
  { path: "/blog/auth0-vs-clerk-vs-firebase-auth", priority: 0.8, changefreq: "monthly" },
  { path: "/blog/posthog-vs-mixpanel-vs-amplitude", priority: 0.8, changefreq: "monthly" },
  { path: "/blog/supabase-vs-planetscale-vs-neon", priority: 0.8, changefreq: "monthly" },
  { path: "/blog/twilio-vs-vonage-vs-plivo", priority: 0.8, changefreq: "monthly" },
  { path: "/blog/linear-vs-jira-vs-asana", priority: 0.8, changefreq: "monthly" },
  { path: "/blog/anthropic-vs-openai-vs-google-ai", priority: 0.8, changefreq: "monthly" },
  { path: "/blog/datadog-vs-new-relic-vs-grafana", priority: 0.8, changefreq: "monthly" },
  { path: "/blog/vercel-vs-netlify-vs-render", priority: 0.8, changefreq: "monthly" },
  { path: "/blog/aws-s3-vs-cloudflare-r2-vs-backblaze-b2", priority: 0.8, changefreq: "monthly" },
  { path: "/blog/switching-from-smithery", priority: 0.7, changefreq: "monthly" },
  // Autopsies (high SEO value)
  { path: "/blog/hubspot-api-autopsy", priority: 0.7, changefreq: "monthly" },
  { path: "/blog/salesforce-api-autopsy", priority: 0.7, changefreq: "monthly" },
  { path: "/blog/twilio-api-autopsy", priority: 0.7, changefreq: "monthly" },
  { path: "/blog/shopify-api-autopsy", priority: 0.7, changefreq: "monthly" },
  // Guides
  { path: "/blog/getting-started-mcp", priority: 0.8, changefreq: "monthly" },
  { path: "/blog/securing-keys-for-agents", priority: 0.6, changefreq: "monthly" },
  { path: "/blog/how-to-evaluate-apis-for-agents", priority: 0.7, changefreq: "monthly" },
  // Articles
  { path: "/blog/agent-cards-invisible", priority: 0.6, changefreq: "monthly" },
  { path: "/blog/agent-native-frontend-stack", priority: 0.6, changefreq: "monthly" },
  { path: "/blog/agent-passport-ranking", priority: 0.5, changefreq: "monthly" },
  { path: "/blog/self-score", priority: 0.5, changefreq: "monthly" },
  { path: "/blog/we-scored-ourselves", priority: 0.5, changefreq: "monthly" },
  { path: "/blog/aag-framework", priority: 0.6, changefreq: "monthly" },
  { path: "/blog/payments-for-agents", priority: 0.5, changefreq: "monthly" },
  { path: "/blog/how-agents-pay", priority: 0.5, changefreq: "monthly" },
  { path: "/blog/how-agents-actually-pay-x402-dogfood", priority: 0.6, changefreq: "monthly" },
  { path: "/blog/firecrawl-vs-scraperapi-vs-apify", priority: 0.7, changefreq: "monthly" },
  { path: "/blog/algolia-vs-typesense-vs-elasticsearch", priority: 0.7, changefreq: "monthly" },
  { path: "/blog/github-actions-vs-gitlab-ci-vs-circleci", priority: 0.7, changefreq: "monthly" },
  { path: "/blog/terraform-cloud-vs-spacelift-vs-env0", priority: 0.7, changefreq: "monthly" },
  { path: "/changelog", priority: 0.4, changefreq: "weekly" },
  { path: "/privacy", priority: 0.3, changefreq: "yearly" },
  { path: "/terms", priority: 0.3, changefreq: "yearly" },
];

function escapeXml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

export const GET: APIRoute = async () => {
  const [services, categories] = await Promise.all([
    getServices(),
    getCategories(),
  ]);

  const now = new Date().toISOString().split("T")[0];

  let xml = `<?xml version="1.0" encoding="UTF-8"?>\n`;
  xml += `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n`;

  // Static pages
  for (const page of STATIC_PAGES) {
    xml += `  <url>\n`;
    xml += `    <loc>${SITE}${escapeXml(page.path)}</loc>\n`;
    xml += `    <changefreq>${page.changefreq}</changefreq>\n`;
    xml += `    <priority>${page.priority}</priority>\n`;
    xml += `  </url>\n`;
  }

  // Dynamic service pages
  for (const service of services) {
    xml += `  <url>\n`;
    xml += `    <loc>${SITE}/service/${escapeXml(service.slug)}</loc>\n`;
    xml += `    <changefreq>weekly</changefreq>\n`;
    xml += `    <priority>0.8</priority>\n`;
    xml += `    <lastmod>${now}</lastmod>\n`;
    xml += `  </url>\n`;
  }

  // Dynamic category leaderboard pages
  for (const cat of categories) {
    xml += `  <url>\n`;
    xml += `    <loc>${SITE}/leaderboard/${escapeXml(cat.slug)}</loc>\n`;
    xml += `    <changefreq>weekly</changefreq>\n`;
    xml += `    <priority>0.8</priority>\n`;
    xml += `    <lastmod>${now}</lastmod>\n`;
    xml += `  </url>\n`;
  }

  xml += `</urlset>`;

  return new Response(xml, {
    headers: {
      "Content-Type": "application/xml",
      "Cache-Control": "public, max-age=3600",
    },
  });
};
