import Link from "next/link";
import { PublicNav } from "./PublicNav";

export type EditorialDetail = {
  index: string;
  eyebrow: string;
  title: string;
  description: string;
  points: string[];
};
export type EditorialPage = {
  slug: string;
  eyebrow: string;
  title: string;
  introduction: string;
  emphasis: string;
  details: EditorialDetail[];
  note: string;
  next: { label: string; href: string };
};

export function PublicEditorial({ page }: { page: EditorialPage }) {
  return <main className="sr-public-page">
    <div className="sr-public-frame">
      <PublicNav />
      <header className="sr-editorial-hero">
        <div className="sr-editorial-hero-head">
          <p className="sr-overline">SignalRankAI / {page.eyebrow}</p>
          <p className="sr-editorial-document">PRODUCT REFERENCE &nbsp;/&nbsp; {page.slug.toUpperCase()}</p>
        </div>
        <h1>{page.title}</h1>
        <div className="sr-editorial-hero-bottom">
          <p>{page.introduction}</p>
          <span className="sr-editorial-emphasis">{page.emphasis}</span>
        </div>
        <div className="sr-editorial-track" aria-hidden="true"><span/><span/><span/><span/><span/><span/></div>
      </header>
      <section className="sr-editorial-content" aria-labelledby="sr-editorial-heading">
        <div className="sr-editorial-heading">
          <p className="sr-overline">The underlying system</p>
          <h2 id="sr-editorial-heading">Designed to be examined.</h2>
          <p>Explore the product&apos;s documented capabilities and safety boundaries. Features and readiness remain governed by deployed configuration and account entitlements.</p>
        </div>
        <div className="sr-editorial-sections">{page.details.map(detail=><article className="sr-editorial-section" key={detail.index}>
          <div className="sr-editorial-index"><span>{detail.index}</span><span>{detail.eyebrow}</span></div>
          <div className="sr-editorial-body">
            <h3>{detail.title}</h3><p>{detail.description}</p>
            <ul>{detail.points.map(point=><li key={point}>{point}</li>)}</ul>
          </div>
        </article>)}</div>
      </section>
      <section className="sr-editorial-bottom" aria-labelledby="sr-reference-note">
        <div><p className="sr-overline">Disclosure / {page.slug}</p><h2 id="sr-reference-note">Verification is part of the product.</h2></div>
        <p>{page.note}</p>
      </section>
      <div className="sr-editorial-next">
        <Link href={page.next.href}>Continue reading: {page.next.label} <span aria-hidden="true">↗</span></Link>
        <Link className="button" href="/login">Open secure account</Link>
      </div>
      <footer className="sr-public-footer"><Link href="/">SignalRankAI</Link><span>Trading involves loss risk. Information is decision support, not a guaranteed outcome.</span><Link href="/risk">Risk disclosure ↗</Link></footer>
    </div>
  </main>;
}
