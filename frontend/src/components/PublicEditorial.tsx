import Link from "next/link";
import { PublicNav } from "./PublicNav";
import { SiteCredit } from "./SiteCredit";
import { WorkspaceLink } from "./WorkspaceLink";
import { Icon } from "./ui/Icon";
import { Notice } from "./ui/primitives";

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

/** Shared layout for every public reference page (pricing, methodology, risk, …). */
export function PublicEditorial({ page, children }: { page: EditorialPage; children?: React.ReactNode }) {
  return <main className="mk-page">
    <PublicNav current={`/${page.slug}`} />
    <div className="mk-container skip-target" id="page-content" tabIndex={-1}>
      <header className="mk-editorial-hero">
        <p className="ui-eyebrow ui-eyebrow--brand">{page.eyebrow}</p>
        <h1>{page.title}</h1>
        <p className="mk-lede">{page.introduction}</p>
        <span className="ui-badge ui-badge--brand ui-badge--plain">{page.emphasis}</span>
      </header>
      {children}
      <section className="mk-editorial-content" aria-label={`${page.eyebrow} details`}>
        {page.details.map(detail=><article className="mk-editorial-section" key={detail.index}>
          <div className="mk-editorial-index"><span>{detail.index}</span><span className="ui-eyebrow">{detail.eyebrow}</span></div>
          <div className="mk-editorial-body">
            <h2>{detail.title}</h2><p>{detail.description}</p>
            <ul>{detail.points.map(point=><li key={point}><Icon name="check"/><span>{point}</span></li>)}</ul>
          </div>
        </article>)}
      </section>
      <div className="mk-editorial-note">
        <Notice tone="warning"><strong>Disclosure.</strong> {page.note}</Notice>
      </div>
      <div className="mk-editorial-next">
        <Link className="ui-link" href={page.next.href}>Continue reading: {page.next.label} <Icon name="arrowRight"/></Link>
        <WorkspaceLink className="ui-btn ui-btn--primary" href="/login">Open secure account</WorkspaceLink>
      </div>
      <SiteCredit navigation />
    </div>
  </main>;
}
