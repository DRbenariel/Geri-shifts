import type { Metadata, Viewport } from 'next';
import { Heebo } from 'next/font/google';
import './globals.css';

const heebo = Heebo({ subsets: ['hebrew', 'latin'], weight: ['300', '400', '500', '700', '800', '900'], variable: '--font-heebo', display: 'swap' });

export const metadata: Metadata = {
  title: 'מערכת סידור עבודה · המערך הגריאטרי',
  description: 'Mockup (fictional data) of the new Geri-shifts UI, superadmin view.',
};
export const viewport: Viewport = { width: 'device-width', initialScale: 1, themeColor: '#E9ECEF' };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="he" dir="rtl" className={heebo.variable}>
      <body>{children}</body>
    </html>
  );
}
