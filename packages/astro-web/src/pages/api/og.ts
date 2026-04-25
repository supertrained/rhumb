import type { APIRoute } from 'astro';
import { ImageResponse } from '@vercel/og';

export const GET: APIRoute = async ({ url }) => {
  const title = url.searchParams.get("title") || "Rhumb — Index ranks. Resolve routes.";
  const subtitle =
    url.searchParams.get("subtitle") ||
    "Agent gateway for service scoring and governed execution";

  const html = {
    type: "div",
    props: {
      style: {
        height: "100%",
        width: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        backgroundColor: "#0B1120",
        padding: "60px 80px",
        fontFamily: "system-ui, sans-serif",
      },
      children: [
        // Top accent line
        {
          type: "div",
          props: {
            style: {
              position: "absolute",
              top: 0,
              left: 0,
              right: 0,
              height: "4px",
              background: "linear-gradient(90deg, #F59E0B, #D97706, #F59E0B)",
            },
          },
        },
        // Logo
        {
          type: "div",
          props: {
            style: {
              display: "flex",
              alignItems: "center",
              marginBottom: "40px",
            },
            children: [
              {
                type: "span",
                props: {
                  style: {
                    fontSize: "32px",
                    fontWeight: 700,
                    color: "#F1F5F9",
                    letterSpacing: "-0.02em",
                  },
                  children: "rhumb",
                },
              },
              {
                type: "span",
                props: {
                  style: { fontSize: "32px", fontWeight: 700, color: "#F59E0B" },
                  children: ".",
                },
              },
            ],
          },
        },
        // Title
        {
          type: "div",
          props: {
            style: {
              fontSize: "56px",
              fontWeight: 700,
              color: "#F1F5F9",
              lineHeight: 1.15,
              letterSpacing: "-0.03em",
              marginBottom: "20px",
              maxWidth: "900px",
            },
            children: title,
          },
        },
        // Subtitle
        {
          type: "div",
          props: {
            style: {
              fontSize: "24px",
              color: "#94A3B8",
              lineHeight: 1.4,
              maxWidth: "700px",
            },
            children: subtitle,
          },
        },
        // Bottom bar
        {
          type: "div",
          props: {
            style: {
              position: "absolute",
              bottom: "40px",
              left: "80px",
              right: "80px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            },
            children: [
              {
                type: "span",
                props: {
                  style: { fontSize: "16px", color: "#64748B" },
                  children: "rhumb.dev",
                },
              },
              {
                type: "div",
                props: {
                  style: { display: "flex", gap: "24px" },
                  children: [
                    {
                      type: "span",
                      props: {
                        style: { fontSize: "14px", color: "#475569" },
                        children: "Index ranks",
                      },
                    },
                    {
                      type: "span",
                      props: {
                        style: { fontSize: "14px", color: "#475569" },
                        children: "·",
                      },
                    },
                    {
                      type: "span",
                      props: {
                        style: { fontSize: "14px", color: "#475569" },
                        children: "Resolve routes",
                      },
                    },
                    {
                      type: "span",
                      props: {
                        style: { fontSize: "14px", color: "#475569" },
                        children: "·",
                      },
                    },
                    {
                      type: "span",
                      props: {
                        style: { fontSize: "14px", color: "#475569" },
                        children: "Pay per call",
                      },
                    },
                  ],
                },
              },
            ],
          },
        },
      ],
    },
  };

  return new ImageResponse(html as any, {
    width: 1200,
    height: 630,
  });
};
