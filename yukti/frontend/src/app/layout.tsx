import type { Metadata } from 'next';
import '../design/tokens.generated.css';
import './globals.css';

export const metadata: Metadata = {
  title: 'Yukti AI — IndianOil Finance & Downstream Intelligence',
  description: 'Voice-first AI agent for Indian Oil Corporation Limited (IndianOil) leadership (Chairman, Director Finance, Director Refineries, Director Marketing). Hands-free financial analytics, refining economics, treasury policy guidance, and NSE:IOC valuation.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body className="antialiased font-sans min-h-screen">
        {children}
      </body>
    </html>
  );
}
