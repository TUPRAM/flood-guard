import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { StudioWorkspace } from "./studio-workspace";
import { WorkspaceHeader } from "./workspace-header";

const noop = () => {};

describe("WorkspaceHeader", () => {
  it("names the current page on the surface's own address", () => {
    const html = renderToStaticMarkup(<WorkspaceHeader activeSurface="studio" language="en" onLanguageChange={noop} />);

    expect(html).toContain('<a href="/public/">Public</a>');
    expect(html).toContain('<a href="/command/">Planning</a>');
    expect(html).toContain('<a href="/studio/" aria-current="page">Studio</a>');
  });

  it("marks the section, not the page, on a page below the surface address", () => {
    const html = renderToStaticMarkup(<WorkspaceHeader activeSurface="planning" language="en" onLanguageChange={noop} surfaceRoot={false} />);

    expect(html).toContain('<a href="/command/" aria-current="true">Planning</a>');
    expect(html).not.toContain('aria-current="page"');
  });

  it("carries the page's case query on every surface link, and the plain address until the query is known", () => {
    const query = "?aoi=aoi-01_mae_sai_core&event=mae_sai_2024";
    const known = renderToStaticMarkup(
      <WorkspaceHeader activeSurface="planning" language="en" onLanguageChange={noop} surfaceRoot={false} hrefFor={(path) => `${path}${query}`} />,
    );
    const pending = renderToStaticMarkup(
      <WorkspaceHeader activeSurface="planning" language="en" onLanguageChange={noop} surfaceRoot={false} hrefFor={() => undefined} />,
    );

    for (const path of ["/public/", "/command/", "/studio/"]) {
      expect(known).toContain(`href="${path}${query.replace("&", "&amp;")}"`);
      expect(pending).toContain(`href="${path}"`);
    }
    expect(known).toContain('aria-label="FloodGuard Planning"');
  });

  it("is a section marker on the historical technical archive and a page marker on the planning evidence report", () => {
    const archive = renderToStaticMarkup(<StudioWorkspace archive />);
    const report = renderToStaticMarkup(<StudioWorkspace />);

    expect(archive).toContain('<a href="/studio/" aria-current="true">Studio</a>');
    expect(archive).not.toContain('aria-current="page"');
    expect(report).toContain('<a href="/studio/" aria-current="page">Studio</a>');
  });
});
