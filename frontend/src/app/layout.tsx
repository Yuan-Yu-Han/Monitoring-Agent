import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SafeGuard Fire Assistant · 安防监控平台",
  description: "火灾与安防监控专业助手（SafeGuard Fire Assistant）",
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
