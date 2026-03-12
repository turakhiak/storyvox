import type { Metadata } from "next";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "StoryVox — Turn Books into Radio Plays",
  description: "Upload any epub and transform it into a fully-voiced radio play with AI-powered screenplay conversion and multi-character voices.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen antialiased">
        {/* Subtle film grain texture */}
        <div className="grain-overlay" />
        {children}
      </body>
    </html>
  );
}
