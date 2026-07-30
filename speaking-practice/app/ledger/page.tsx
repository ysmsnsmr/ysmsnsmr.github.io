import type { Metadata } from "next";
import VoiceLedgerApp from "@/components/VoiceLedgerApp";

export const metadata: Metadata = {
  title: "Voice Practice Ledger",
  description: "Paste and save concise Voice practice notes and next missions."
};

export default function LedgerPage() {
  return <VoiceLedgerApp />;
}
