import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ProcessIQ — AI Process Optimization",
  description: "AI-powered business process optimization advisor",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen bg-dark-bg">{children}</div>
      </body>
    </html>
  );
}
