import Image from "next/image";
import Link from "next/link";

type SurfaceIconName = "public" | "command" | "studio";

function SurfaceIcon({ name }: { name: SurfaceIconName }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      {name === "public" && (
        <>
          <path d="M4 19.5v-9L12 4l8 6.5v9" />
          <path d="M8 20v-6h8v6M9 10h6" />
        </>
      )}
      {name === "command" && (
        <>
          <path d="m4 6 5-2 6 2 5-2v14l-5 2-6-2-5 2Z" />
          <path d="M9 4v14M15 6v14M6.5 13l3-2 3 1 4.5-3" />
        </>
      )}
      {name === "studio" && (
        <>
          <path d="M9 3h6M10 3v5l-5 9a2.5 2.5 0 0 0 2.2 4h9.6a2.5 2.5 0 0 0 2.2-4l-5-9V3" />
          <path d="M7.5 15h9M9.5 11h5" />
        </>
      )}
    </svg>
  );
}

export default function SurfaceChooser() {
  return (
    <main className="surface-chooser" id="main-content" lang="en">
      <header className="chooser-header">
        <Link className="chooser-logo" href="/" aria-label="FloodGuard Thailand home">
          <Image src="/icon.svg" width={44} height={44} alt="" priority />
          <span>
            <b>FloodGuard</b>
            <small>Thailand planning platform</small>
          </span>
        </Link>
        <div className="chooser-header-context">
          <span>Mae Sai, Chiang Rai</span>
          <strong>Flood preparedness intelligence</strong>
        </div>
      </header>

      <div className="chooser-shell">
        <section className="chooser-hero" aria-labelledby="chooser-title">
          <div className="chooser-hero-copy">
            <p className="eyebrow">Preparedness planning platform</p>
            <h1 id="chooser-title">One platform. Three planning views.</h1>
            <p className="chooser-lead">
              Choose the workspace for household preparation, area planning, or evidence review.
            </p>
            <p className="chooser-thai" lang="th">
              เลือกพื้นที่ทำงานสำหรับการเตรียมพร้อม การวางแผนพื้นที่ หรือการตรวจสอบหลักฐาน
            </p>
          </div>
          <aside className="chooser-hero-summary" aria-label="Platform coverage">
            <span>Mae Sai</span>
            <strong>Connected planning intelligence</strong>
            <p>Public guidance, command decisions, and research evidence share one source-aware platform.</p>
          </aside>
        </section>

        <section className="chooser-surface-section" aria-labelledby="workspace-title">
          <div className="chooser-section-heading">
            <div>
              <p className="eyebrow">Choose your workspace</p>
              <h2 id="workspace-title">Continue by role</h2>
            </div>
            <p>Each view is designed around a different planning responsibility.</p>
          </div>

          <nav className="surface-grid" aria-label="FloodGuard planning workspaces">
            <Link className="surface-card surface-card-public" href="/public/" prefetch={false}>
              <div className="surface-card-topline">
                <span className="surface-number">01</span>
                <span className="surface-icon"><SurfaceIcon name="public" /></span>
              </div>
              <div className="surface-card-copy">
                <p>For households and communities</p>
                <h2>Public preparedness</h2>
                <span>Review the area, important facilities, official contacts, and your household plan.</span>
              </div>
              <div className="surface-card-action"><span>Open public view</span><b aria-hidden="true">→</b></div>
            </Link>

            <Link className="surface-card surface-card-command" href="/command/" prefetch={false}>
              <div className="surface-card-topline">
                <span className="surface-number">02</span>
                <span className="surface-icon"><SurfaceIcon name="command" /></span>
              </div>
              <div className="surface-card-copy">
                <p>For planners and coordinators</p>
                <h2>Planning command center</h2>
                <span>Compare area priorities, inspect the Mae Sai map, and review planning evidence.</span>
              </div>
              <div className="surface-card-action"><span>Open command center</span><b aria-hidden="true">→</b></div>
            </Link>

            <Link className="surface-card surface-card-studio" href="/studio/" prefetch={false}>
              <div className="surface-card-topline">
                <span className="surface-number">03</span>
                <span className="surface-icon"><SurfaceIcon name="studio" /></span>
              </div>
              <div className="surface-card-copy">
                <p>For research and validation</p>
                <h2>Research &amp; validation studio</h2>
                <span>Examine technical verification, observed-data validation, and operational readiness.</span>
              </div>
              <div className="surface-card-action"><span>Open research studio</span><b aria-hidden="true">→</b></div>
            </Link>
          </nav>
        </section>

        <aside className="chooser-guidance" aria-label="Current-information guidance">
          <span className="chooser-guidance-mark" aria-hidden="true">!</span>
          <div>
            <strong>Use current official information when taking action.</strong>
            <p>Check DDPM and local-authority updates for current conditions and instructions.</p>
          </div>
          <span className="chooser-guidance-meta">Source time and confidence are shown in each workspace.</span>
        </aside>
      </div>

      <footer className="chooser-footer">
        <span>FloodGuard Thailand</span>
        <span>Mae Sai flood preparedness planning</span>
      </footer>
    </main>
  );
}
