import type { Metadata } from "next";
import "leaflet/dist/leaflet.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "ThaiAir — แผนที่พยากรณ์ PM2.5 กรุงเทพฯ",
  description: "ข้อมูล PM2.5 ล่าสุดและพยากรณ์ล่วงหน้า 24 ชั่วโมงรอบกรุงเทพฯ",
};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return (
    <html lang="th">
      <body>{children}</body>
    </html>
  );
}
