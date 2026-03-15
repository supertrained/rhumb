import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import sitemap from '@astrojs/sitemap';
import vercel from '@astrojs/vercel';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  site: 'https://rhumb.dev',
  output: 'server',
  adapter: vercel(),
  integrations: [
    react(),
    sitemap(),
  ],
  vite: {
    plugins: [tailwindcss()],
  },
  redirects: {
    '/services': '/leaderboard',
    '/services/[slug]': '/service/[slug]',
    '/services/[slug]/failures': '/service/[slug]',
    '/services/[slug]/history': '/service/[slug]',
  },
});
