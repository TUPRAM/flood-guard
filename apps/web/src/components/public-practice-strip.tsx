import { PublicAppIcon } from "@/components/public-app-icon";
import type { PracticeView } from "@/lib/public-practice";

interface PublicPracticeStripProps {
  view: PracticeView;
  /** The question of the page the strip stands on. */
  prompt: string;
  /** A line of the page's own under the question (the SOS page says that no call is placed). */
  note?: string;
}

/**
 * The practice scenario on a Public page that has no map (Report, Prepare, SOS): which hour of the replay is shown,
 * what it says for the example home, and what a household can practise on this page. It carries the sentence and
 * the tone of the banner on the Home map, so the five pages tell one story, and it says on every page what the
 * replay is not.
 */
export function PublicPracticeStrip({ view, prompt, note }: PublicPracticeStripProps) {
  return (
    <aside className="public-practice-strip" data-tone={view.tone} aria-label={view.copy.noteTitle}>
      <p className="public-practice-strip__label" data-public-not-a-warning>
        <strong>{view.copy.noteTitle} · {view.moment}</strong>
        <span>{view.copy.noteBoundary}</span>
      </p>
      <p className="public-practice-strip__state">
        <PublicAppIcon name={view.tone === "calm" ? "check" : "hazard"} />
        <span>{view.banner}</span>
      </p>
      <p className="public-practice-strip__prompt">{prompt}</p>
      {note ? <p className="public-practice-strip__note">{note}</p> : null}
    </aside>
  );
}
