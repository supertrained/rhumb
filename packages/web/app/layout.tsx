import type { ReactNode } from "react";

import { Navigation } from "../components/Navigation";
import "../styles/globals.css";

export default function RootLayout({ children }: { children: ReactNode }): JSX.Element {
  return (
    <html lang="en">
      <body>
        <Navigation />
        <main style={{ padding: 24 }}>{children}</main>
      </body>
    </html>
  );
}
