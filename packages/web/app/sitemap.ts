import type { MetadataRoute } from "next";
import { getServices, getCategories } from "../lib/api";

const BASE_URL = "https://rhumb.dev";
const NOW = new Date();

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  // Static routes
  const staticRoutes: MetadataRoute.Sitemap = [
    {
      url: `${BASE_URL}/`,
      lastModified: NOW,
      changeFrequency: "daily",
      priority: 1.0,
    },
    {
      url: `${BASE_URL}/leaderboard`,
      lastModified: NOW,
      changeFrequency: "daily",
      priority: 0.9,
    },
    {
      url: `${BASE_URL}/search`,
      lastModified: NOW,
      changeFrequency: "weekly",
      priority: 0.7,
    },
    {
      url: `${BASE_URL}/blog`,
      lastModified: NOW,
      changeFrequency: "monthly",
      priority: 0.6,
    },
    {
      url: `${BASE_URL}/blog/payments-for-agents`,
      lastModified: NOW,
      changeFrequency: "monthly",
      priority: 0.6,
    },
    {
      url: `${BASE_URL}/services`,
      lastModified: NOW,
      changeFrequency: "weekly",
      priority: 0.8,
    },
  ];

  // Dynamic service routes
  let serviceRoutes: MetadataRoute.Sitemap = [];
  try {
    const services = await getServices();
    serviceRoutes = services.map((service) => ({
      url: `${BASE_URL}/service/${service.slug}`,
      lastModified: NOW,
      changeFrequency: "weekly" as const,
      priority: 0.8,
    }));
  } catch {
    // Silently skip dynamic service routes if fetch fails
  }

  // Dynamic leaderboard category routes
  let categoryRoutes: MetadataRoute.Sitemap = [];
  try {
    const categories = await getCategories();
    categoryRoutes = categories.map((cat) => ({
      url: `${BASE_URL}/leaderboard/${cat.slug}`,
      lastModified: NOW,
      changeFrequency: "daily" as const,
      priority: 0.85,
    }));
  } catch {
    // Silently skip dynamic category routes if fetch fails
  }

  return [...staticRoutes, ...serviceRoutes, ...categoryRoutes];
}
