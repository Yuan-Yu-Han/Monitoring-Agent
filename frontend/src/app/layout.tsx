import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FireGuard AI Monitor",
  description: "AI-powered fire & security monitoring dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh">
      <body className="antialiased">{children}</body>
    </html>
  );
}
