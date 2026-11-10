import type { Metadata } from "next";
import { PublicNav } from "../../components/PublicNav";
import { SiteCredit } from "../../components/SiteCredit";
import { TrackRecord } from "../../components/TrackRecord";

export const metadata: Metadata = {
  title: "Live track record",
  description: "Every signal SignalRankAI delivered and how it closed, misses included, by market.",
};

export default function TrackRecordPage() {
  return <>
    <PublicNav current="/track-record"/>
    <main id="page-content" className="mk-container tr-page">
      <header className="tr-head">
        <p className="mk-eyebrow">Live record</p>
        <h1>Every call, on the record.</h1>
        <p>These are the signals we actually delivered and how each one closed, across crypto, forex, indices, stocks and commodities. Misses are included. Results are in R, the multiple of the risk each trade planned, before fees and slippage.</p>
      </header>
      <TrackRecord/>
      <p className="tr-note">Past results do not guarantee future results. Signals are research to help your own decisions, not financial advice. We never hold or trade your money.</p>
    </main>
    <SiteCredit/>
  </>;
}
