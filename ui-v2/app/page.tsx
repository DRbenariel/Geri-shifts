'use client';
import AppShell from '@/components/AppShell';
import { StoreProvider } from '@/lib/store';

export default function Home() {
  return <StoreProvider><AppShell /></StoreProvider>;
}
