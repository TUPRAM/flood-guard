"use client";

/**
 * The panels around the map of the Command exercise replay: the banner with its information drawer (region A), the
 * navigation (C), the round map tools (E), the legend (G), the watermark and the map credits (H), the one-line notice
 * (I) and the help sheet.
 *
 * The page is an exercise and after-action tool on a reconstructed 2024 event: the banner says so on every screen
 * and cannot be dismissed, and the drawer lists the permitted use, the assumptions, the limits and the sources of the
 * replay data.
 */

import { ArrowRight, ChevronDown, ChevronUp, CircleHelp, ClipboardList, FileText, Info, Layers, ListChecks, LocateFixed, Map as MapIcon, Maximize2, Menu, Minimize2, Minus, Plus, Scan, Search, Settings2, X } from "lucide-react";
import { Fragment, useEffect, useId, useRef, useState, type ReactNode, type Ref } from "react";

import { formatDateWithYear, lowConfidenceRgba, rgbaCss, type Language, type Localized, type TimelineManifest } from "@/lib/flood-timeline";
import { COMMAND_EXERCISE_MENU, COMMAND_HELP_ACT, COMMAND_HELP_ACT_STEPS, COMMAND_NEAR } from "@/lib/flood-timeline-command-act-copy";
import {
  COMMAND_BANNER,
  COMMAND_CREDITS,
  COMMAND_DRAWER,
  COMMAND_DRAWER_NOT,
  COMMAND_DRAWER_SOURCES,
  COMMAND_FIGURES,
  COMMAND_HELP,
  COMMAND_HELP_KEYS,
  COMMAND_LANE_ORDER,
  COMMAND_LEGEND,
  COMMAND_MAP,
  COMMAND_NAV,
  COMMAND_TOOLS,
  commandBannerParts,
  commandDataLine,
  commandDataTag,
  commandDrawerHeading,
  commandLaneMeaning,
  commandLaneTag,
  commandScaleLabel,
  commandSourceSpan,
  commandText,
} from "@/lib/flood-timeline-command-copy";
import type { CommandMode } from "@/lib/flood-timeline-command-feed";
import { EXERCISE_URGENCIES, exerciseMarkerSpec, type ExerciseUrgency } from "@/lib/flood-timeline-command-incidents";
import { COMMAND_EXERCISE, COMMAND_LEGEND_REPORTS, COMMAND_MARKERS, COMMAND_MODE, COMMAND_URGENCY, commandDeviceSign, commandWaitingShort } from "@/lib/flood-timeline-command-reports-copy";
import { COMMAND_ENVELOPE_RGBA, COMMAND_WATER_RGBA, COMMAND_WET_ROAD, commandScaleBar } from "@/lib/flood-timeline-command-map";
import { localizedText } from "@/lib/flood-timeline-copy";

import act from "./mae-sai-command-act.module.css";
import type { CommandBasemap, CommandFitTarget, CommandMapView } from "./mae-sai-command-map";
import { ClusterGlyph, exerciseMarkerNodes, MarkerGlyph, NoReportsGlyph, placeRecordMarkerNodes } from "./mae-sai-command-markers";
import styles from "./mae-sai-command-exercise.module.css";

/** The address of this page while it is tried out; it moves to the Command root in a later change. */
export const COMMAND_EXERCISE_ROUTE = "/command/exercise/";

const pick = commandText;

// --- A. Banner ---------------------------------------------------------------------------------------------

export function CommandBanner({ language, onInfo, infoOpen, infoRef }: { language: Language; onInfo: () => void; infoOpen: boolean; infoRef?: Ref<HTMLButtonElement> }) {
  const [tag, ...rest] = commandBannerParts(language);
  return (
    <div className={styles.banner} role="region" data-region="A" aria-label={pick(COMMAND_BANNER.label, language)} lang={language}>
      <span className={styles.bannerTag}>{tag}</span>
      {/* The dots between the parts are text, so the line reads the same when it is copied, translated or read aloud. */}
      <p className={styles.bannerText} data-command-banner>
        {rest.map((part, index) => (
          <Fragment key={part}>
            <span className={styles.bannerPart}>{part}{index < rest.length - 1 && <span className={styles.bannerSep}> ·</span>}</span>
            {index < rest.length - 1 ? " " : null}
          </Fragment>
        ))}
      </p>
      <button ref={infoRef} type="button" className={styles.infoButton} onClick={onInfo} aria-haspopup="dialog" aria-expanded={infoOpen} aria-label={pick(COMMAND_BANNER.info, language)} title={pick(COMMAND_DRAWER.title, language)} data-command-info>
        <Info size={20} aria-hidden="true" />
      </button>
    </div>
  );
}

/** A native modal dialog: the browser keeps the focus inside it and closes it on Escape. */
export function ModalDialog({ open, onClose, className, labelledBy, language, name, children }: {
  open: boolean; onClose: () => void; className: string; labelledBy: string; language: Language; name: string; children: ReactNode;
}) {
  const element = useRef<HTMLDialogElement | null>(null);
  useEffect(() => {
    const dialog = element.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return (
    <dialog ref={element} className={className} aria-labelledby={labelledBy} lang={language} data-command-dialog={name} onClose={onClose}
      onClick={(event) => { if (event.target === element.current) onClose(); }}>
      {children}
    </dialog>
  );
}

/** A sentence of the replay data: in Thai when a rendering is known, otherwise the English original, marked as such. */
function DataSentence({ text, language }: { text: string; language: Language }) {
  const shown = localizedText(text, language);
  if (shown.lang === language) return <>{shown.text}</>;
  return <><span className={styles.original}>{pick(COMMAND_DRAWER.englishOriginal, language)}</span><span lang="en">{shown.text}</span></>;
}

/**
 * What the drawer says. Its own sentences are the page's; the permitted use, the assumptions, the limits and the
 * sources are the replay data's, shown as they are written there.
 */
export function CommandInfoBody({ language, manifest }: { language: Language; manifest: TimelineManifest | null }) {
  const t = (entry: Localized) => pick(entry, language);
  const built = manifest?.generated_at ? formatDateWithYear(manifest.generated_at, language) : null;
  return (
    <div className={styles.drawerBody}>
      <section>
        <h3>{t(COMMAND_DRAWER.whatTitle)}</h3>
        <p>{t(COMMAND_DRAWER.what)}</p>
      </section>
      <section>
        <h3>{t(COMMAND_DRAWER.notTitle)}</h3>
        <ul>{COMMAND_DRAWER_NOT.map((key) => <li key={key}>{t(COMMAND_DRAWER[key])}</li>)}</ul>
      </section>
      {manifest?.permitted_use && (
        <section data-command-drawer="permitted">
          <h3>{t(COMMAND_DRAWER.permittedTitle)}</h3>
          <p><DataSentence text={manifest.permitted_use} language={language} /></p>
        </section>
      )}
      <section>
        <h3>{t(COMMAND_DRAWER.confidenceTitle)}</h3>
        <p>{t(COMMAND_DRAWER.confidence)}</p>
        <p>{t(COMMAND_DRAWER.townBias)}</p>
        <p>{t(COMMAND_DRAWER.rounding)}</p>
      </section>
      {manifest && (
        <>
          <section data-command-drawer="limits">
            <h3>{commandDrawerHeading("limits", manifest.limitations.length, language)}</h3>
            <ul>{manifest.limitations.map((text) => <li key={text}><DataSentence text={text} language={language} /></li>)}</ul>
          </section>
          <details data-command-drawer="assumptions">
            <summary>{commandDrawerHeading("assumptions", manifest.assumptions.length, language)}</summary>
            <ol>{manifest.assumptions.map((text) => <li key={text}><DataSentence text={text} language={language} /></li>)}</ol>
          </details>
          <details data-command-drawer="sources" open>
            <summary>{commandDrawerHeading("sources", manifest.sources.length, language)}</summary>
            <dl>
              {manifest.sources.map((source) => (
                <div key={source.id}>
                  <dt lang="en">{source.name}</dt>
                  <dd>{t(COMMAND_DRAWER_SOURCES.licence)}: <span lang="en">{source.licence}</span></dd>
                  <dd>{t(COMMAND_DRAWER_SOURCES.dated)}: <span lang="en">{source.timestamp}</span></dd>
                  <dd lang="en">{source.attribution}</dd>
                </div>
              ))}
            </dl>
          </details>
        </>
      )}
      <section>
        <h3>{t(COMMAND_DRAWER.lanesTitle)}</h3>
        <p>{t(COMMAND_DRAWER.lanesIntro)}</p>
        <ul className={styles.laneList}>
          {COMMAND_LANE_ORDER.map((lane) => <li key={lane}><b data-lane={lane}>{commandLaneTag(lane, language)}</b><span>{commandLaneMeaning(lane, language)}</span></li>)}
        </ul>
      </section>
      <section>
        <h3>{t(COMMAND_DRAWER.deviceTitle)}</h3>
        <p>{t(COMMAND_DRAWER.device)}</p>
      </section>
      <section data-command-drawer="thai">
        <h3>{t(COMMAND_DRAWER.thaiTitle)}</h3>
        <p>{t(COMMAND_DRAWER.thaiNote)}</p>
      </section>
      {manifest && built && (
        <p className={styles.dataLine} data-command-drawer="data">{commandDataLine(manifest.revision, built, commandSourceSpan(manifest.source_timestamp, language), language)}</p>
      )}
    </div>
  );
}

export function CommandInfoDrawer({ open, onClose, language, manifest }: { open: boolean; onClose: () => void; language: Language; manifest: TimelineManifest | null }) {
  const title = useId();
  return (
    <ModalDialog open={open} onClose={onClose} className={styles.drawer} labelledBy={title} language={language} name="info">
      <div className={styles.dialogHead}>
        <h2 id={title}>{pick(COMMAND_DRAWER.title, language)}</h2>
        <button type="button" className={styles.closeButton} onClick={onClose} aria-label={pick(COMMAND_DRAWER.close, language)}><X size={20} aria-hidden="true" /></button>
      </div>
      <CommandInfoBody language={language} manifest={manifest} />
    </ModalDialog>
  );
}

export function CommandHelpSheet({ open, onClose, onAbout, language }: { open: boolean; onClose: () => void; onAbout: () => void; language: Language }) {
  const title = useId();
  const t = (entry: Localized) => pick(entry, language);
  return (
    <ModalDialog open={open} onClose={onClose} className={styles.sheet} labelledBy={title} language={language} name="help">
      <div className={styles.dialogHead}>
        <h2 id={title}>{t(COMMAND_HELP.title)}</h2>
        <button type="button" className={styles.closeButton} onClick={onClose} aria-label={t(COMMAND_DRAWER.close)}><X size={20} aria-hidden="true" /></button>
      </div>
      <div className={styles.sheetBody}>
        <p>{t(COMMAND_HELP.intro)}</p>
        <h3>{t(COMMAND_HELP_ACT.title)}</h3>
        <ol className={act.helpSteps} data-command-help-steps>
          {COMMAND_HELP_ACT_STEPS.map((step) => <li key={step}>{t(COMMAND_HELP_ACT[step])}</li>)}
        </ol>
        <h3>{t(COMMAND_HELP.keys)}</h3>
        <dl className={styles.keys}>
          {COMMAND_HELP_KEYS.map((row) => (
            <div key={row.text} style={{ display: "contents" }}>
              <dt>{row.keys.map((key) => <kbd key={key}>{key}</kbd>)}</dt>
              <dd>{t(COMMAND_HELP[row.text])}</dd>
            </div>
          ))}
        </dl>
        <p className={styles.hotlines}>{t(COMMAND_HELP.hotlines)}</p>
        <button type="button" className={styles.linkButton} onClick={onAbout}>{t(COMMAND_HELP.more)}</button>
      </div>
    </ModalDialog>
  );
}

// --- C. Navigation -----------------------------------------------------------------------------------------

/** What the exercise menu of the navigation opens: the facilitator's setup, the exercise log and the situation brief. */
export interface CommandExerciseMenu {
  open: boolean;
  onToggle: (open: boolean) => void;
  onSetup: () => void;
  onLog: () => void;
  onSituation: () => void;
}

/** The three entries of the exercise menu, in the order a facilitator uses them. */
function ExerciseEntries({ language, exercise, layout }: { language: Language; exercise: CommandExerciseMenu; layout: "panel" | "menu" }) {
  const t = (entry: Localized) => pick(entry, language);
  const entries = [
    { id: "setup", label: COMMAND_EXERCISE_MENU.setup, icon: <Settings2 size={18} aria-hidden="true" />, open: exercise.onSetup },
    { id: "log", label: COMMAND_EXERCISE_MENU.log, icon: <ListChecks size={18} aria-hidden="true" />, open: exercise.onLog },
    { id: "situation", label: COMMAND_EXERCISE_MENU.situation, icon: <FileText size={18} aria-hidden="true" />, open: exercise.onSituation },
  ];
  return (
    <>
      {entries.map((entry) => (
        <button key={entry.id} type="button" className={layout === "menu" ? styles.navItem : act.menuItem} onClick={entry.open} aria-haspopup="dialog" data-command-exercise-item={entry.id}>
          {layout === "menu" ? <span>{entry.icon}{t(entry.label)}</span> : <>{entry.icon}<span>{t(entry.label)}</span></>}
        </button>
      ))}
    </>
  );
}

/**
 * The entries of the pill. The site's sections and the language are in the shared site header above the page
 * (`WorkspaceHeader`, as on every other page), so the pill holds what only this page has: the exercise menu and help.
 */
function NavItems({ language, onHelp, exercise }: { language: Language; onHelp: () => void; exercise?: CommandExerciseMenu }) {
  const t = (entry: Localized) => pick(entry, language);
  return (
    <>
      {exercise && (
        <button type="button" className={styles.navItem} onClick={() => exercise.onToggle(!exercise.open)} aria-expanded={exercise.open} title={t(COMMAND_EXERCISE_MENU.menu)} data-command-exercise-menu>
          <span className={act.navExercise}><ClipboardList size={16} aria-hidden="true" />{t(COMMAND_EXERCISE_MENU.label)}<ChevronDown size={14} aria-hidden="true" /></span>
        </button>
      )}
      <button type="button" className={`${styles.navItem} ${styles.navRound}`} onClick={onHelp} aria-haspopup="dialog" aria-label={t(COMMAND_NAV.help)} title={`${t(COMMAND_NAV.help)} ( ? )`} data-command-help>
        <span><CircleHelp size={20} aria-hidden="true" /><span className={styles.navLabel}>{t(COMMAND_NAV.help)}</span></span>
      </button>
    </>
  );
}

/** The navigation pill of a desktop, and on a tablet one menu button that opens the same entries. */
export function CommandNav({ language, menuOpen, onMenu, onHelp, basemap, onBasemap, exercise, navRef }: {
  language: Language;
  menuOpen: boolean;
  onMenu: (open: boolean) => void;
  onHelp: () => void;
  basemap: CommandBasemap;
  onBasemap: () => void;
  /** The exercise menu: on a desktop a button of the pill with its own small panel, on a tablet three entries of the menu. */
  exercise?: CommandExerciseMenu;
  navRef?: Ref<HTMLElement>;
}) {
  const t = (entry: Localized) => pick(entry, language);
  const exercisePanel = useRef<HTMLDivElement | null>(null);
  const exerciseOpen = exercise?.open ?? false;
  // The panel takes the keyboard focus when it opens, so its entries are the next thing a key reaches.
  useEffect(() => {
    if (exerciseOpen) exercisePanel.current?.querySelector<HTMLElement>("button")?.focus({ preventScroll: true });
  }, [exerciseOpen]);
  return (
    <>
      <nav ref={navRef} className={styles.nav} data-region="C" data-clear-panel aria-label={t(COMMAND_NAV.label)} lang={language}>
        <NavItems language={language} onHelp={onHelp} exercise={exercise} />
      </nav>
      {exercise?.open && (
        <div ref={exercisePanel} className={`${styles.panel} ${act.exerciseMenu}`} role="group" aria-label={t(COMMAND_EXERCISE_MENU.menu)} lang={language} data-command-exercise-panel>
          <ExerciseEntries language={language} exercise={exercise} layout="panel" />
        </div>
      )}
      <button type="button" className={`${styles.tool} ${styles.menuButton}`} onClick={() => onMenu(!menuOpen)} aria-expanded={menuOpen} aria-label={t(COMMAND_NAV.menu)} title={t(COMMAND_NAV.menu)} data-command-menu data-clear-panel>
        {menuOpen ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
      </button>
      {menuOpen && (
        <nav className={`${styles.panel} ${styles.menu}`} aria-label={t(COMMAND_NAV.label)} lang={language} data-command-menu-panel data-clear-panel>
          <NavItems language={language} onHelp={() => { onMenu(false); onHelp(); }} />
          {exercise && (
            <>
              <hr />
              <ExerciseEntries language={language} layout="menu"
                exercise={{ ...exercise, onSetup: () => { onMenu(false); exercise.onSetup(); }, onLog: () => { onMenu(false); exercise.onLog(); }, onSituation: () => { onMenu(false); exercise.onSituation(); } }} />
            </>
          )}
          <hr />
          <button type="button" className={styles.navItem} onClick={onBasemap}>
            <span>{t(COMMAND_TOOLS.basemap)}: {t(basemap === "street" ? COMMAND_TOOLS.basemapStreet : COMMAND_TOOLS.basemapTerrain)}</span>
          </button>
        </nav>
      )}
    </>
  );
}

// --- E. Tool rail ------------------------------------------------------------------------------------------

export function CommandToolRail({ language, focus, basemap, nextFit, viewOpen, findOpen = false, disabled, onView, onBasemap, onZoom, onFit, onFind, onFocus, railRef }: {
  language: Language;
  focus: boolean;
  basemap: CommandBasemap;
  /** What the fit button shows next: the town, then the whole district, in turn. */
  nextFit: CommandFitTarget;
  viewOpen: boolean;
  /** The find-place box is open. */
  findOpen?: boolean;
  /** True until the map is ready. */
  disabled: boolean;
  onView: () => void;
  onBasemap: () => void;
  onZoom: (delta: number) => void;
  onFit: () => void;
  onFind?: () => void;
  onFocus: () => void;
  railRef?: Ref<HTMLDivElement>;
}) {
  const t = (entry: Localized) => pick(entry, language);
  const basemapLabel = `${t(COMMAND_TOOLS.basemap)}: ${t(basemap === "street" ? COMMAND_TOOLS.basemapStreet : COMMAND_TOOLS.basemapTerrain)}`;
  const fitLabel = t(nextFit === "town" ? COMMAND_TOOLS.fitTown : COMMAND_TOOLS.fitDistrict);
  const focusLabel = t(focus ? COMMAND_TOOLS.focusOff : COMMAND_TOOLS.focusOn);
  return (
    <div ref={railRef} className={styles.rail} data-region="E" data-clear-panel role="group" aria-label={t(COMMAND_TOOLS.label)} lang={language}>
      <button type="button" className={styles.tool} onClick={onView} aria-expanded={viewOpen} aria-label={t(COMMAND_TOOLS.view)} title={t(COMMAND_TOOLS.view)} data-command-tool="view">
        <Layers size={20} aria-hidden="true" />
      </button>
      <button type="button" className={`${styles.tool} ${styles.toolBasemap}`} onClick={onBasemap} disabled={disabled} aria-label={basemapLabel} title={basemapLabel} data-command-tool="basemap" data-basemap={basemap}>
        <MapIcon size={20} aria-hidden="true" />
      </button>
      <button type="button" className={styles.tool} onClick={() => onZoom(1)} disabled={disabled} aria-label={t(COMMAND_TOOLS.zoomIn)} title={t(COMMAND_TOOLS.zoomIn)} data-command-tool="zoom-in">
        <Plus size={20} aria-hidden="true" />
      </button>
      <button type="button" className={styles.tool} onClick={() => onZoom(-1)} disabled={disabled} aria-label={t(COMMAND_TOOLS.zoomOut)} title={t(COMMAND_TOOLS.zoomOut)} data-command-tool="zoom-out">
        <Minus size={20} aria-hidden="true" />
      </button>
      <button type="button" className={styles.tool} onClick={onFit} disabled={disabled} aria-label={fitLabel} title={fitLabel} data-command-tool="fit" data-fit={nextFit}>
        {nextFit === "town" ? <LocateFixed size={20} aria-hidden="true" /> : <Scan size={20} aria-hidden="true" />}
      </button>
      <button type="button" className={styles.tool} onClick={onFind} disabled={disabled} aria-expanded={findOpen} aria-label={t(COMMAND_TOOLS.find)} title={t(COMMAND_TOOLS.find)} data-command-tool="find">
        <Search size={20} aria-hidden="true" />
      </button>
      <button type="button" className={styles.tool} onClick={onFocus} aria-pressed={focus} aria-label={focusLabel} title={`${focusLabel} ( F )`} data-command-tool="focus">
        {focus ? <Minimize2 size={20} aria-hidden="true" /> : <Maximize2 size={20} aria-hidden="true" />}
      </button>
    </div>
  );
}

/** What the view popover offers for the exercise: its invented items, and the pause when a life-at-risk item arrives. */
export interface CommandExerciseOptions {
  /** How many invented items the exercise file holds. */
  count: number;
  items: boolean;
  onItems: (shown: boolean) => void;
  pause: boolean;
  onPause: (pause: boolean) => void;
}

/**
 * The view popover: the Rescue view (the only one the page has; a view that is not built is not offered), the key
 * facilities (off until asked for), and the options of the exercise.
 */
export function CommandViewPopover({ language, facilities, facilityCount, onFacilities, exercise, onClose, popoverRef }: {
  language: Language;
  facilities: boolean;
  facilityCount: number;
  onFacilities: (visible: boolean) => void;
  exercise?: CommandExerciseOptions;
  onClose: () => void;
  popoverRef?: Ref<HTMLDivElement>;
}) {
  const t = (entry: Localized) => pick(entry, language);
  const title = useId();
  return (
    <div ref={popoverRef} className={`${styles.panel} ${styles.popover}`} role="group" aria-labelledby={title} lang={language} data-command-popover="view" data-clear-panel>
      <div className={styles.popoverHead}>
        <h2 id={title} tabIndex={-1} data-command-panel-title>{t(COMMAND_TOOLS.viewTitle)}</h2>
        <button type="button" className={styles.iconButton} onClick={onClose} aria-label={t(COMMAND_TOOLS.close)}><X size={18} aria-hidden="true" /></button>
      </div>
      {/* The page has one view: it is named, not offered as a choice of one. */}
      <p className={styles.viewNow} lang={language} data-command-view="rescue">
        <strong>{t(COMMAND_TOOLS.rescue)}</strong>
        <small>{t(COMMAND_TOOLS.rescueNote)}</small>
      </p>
      <fieldset className={styles.choiceGroup}>
        <legend className={styles.srOnly}>{t(COMMAND_TOOLS.facilities)}</legend>
        <label className={styles.choice} lang={language}>
          <input type="checkbox" checked={facilities} onChange={(event) => onFacilities(event.currentTarget.checked)} data-command-facilities />
          <span>{t(COMMAND_TOOLS.facilities)} ({facilityCount})</span>
          <small>{t(COMMAND_TOOLS.facilitiesNote)}</small>
        </label>
      </fieldset>
      {exercise && (
        <fieldset className={styles.choiceGroup} data-command-exercise-options>
          <legend className={styles.choiceLegend}>{t(COMMAND_MODE.exercise)}</legend>
          <label className={styles.choice} lang={language}>
            <input type="checkbox" checked={exercise.items} onChange={(event) => exercise.onItems(event.currentTarget.checked)} data-command-items />
            <span>{t(COMMAND_MODE.items)} ({exercise.count})</span>
            <small>{t(COMMAND_MODE.itemsNote)}</small>
          </label>
          <label className={styles.choice} lang={language}>
            <input type="checkbox" checked={exercise.pause} disabled={!exercise.items} onChange={(event) => exercise.onPause(event.currentTarget.checked)} data-command-pause />
            <span>{t(COMMAND_MODE.pause)}</span>
            <small>{t(COMMAND_MODE.pauseNote)}</small>
          </label>
        </fieldset>
      )}
    </div>
  );
}

// --- G. Legend ---------------------------------------------------------------------------------------------

const STAR_PATH = "M12 1.8l3.1 6.6 7.2.9-5.3 5 1.4 7.1L12 17.9l-6.4 3.5L7 14.3l-5.3-5 7.2-.9z";
/** The small flag of the staging point: the same drawing as on the map. */
export const STAGING_FLAG_PATH = "M6 21V4h11l-2.4 4L17 12H6";
const LOW_STRIPE = rgbaCss(lowConfidenceRgba(COMMAND_WATER_RGBA.shallow, true));
const LOW_WASH = rgbaCss(lowConfidenceRgba(COMMAND_WATER_RGBA.shallow, false));
/** The season envelope as this page draws it: dark ink stripes with a white edge, running the other way than the low-confidence hatch. */
const ENVELOPE_SAMPLE = `repeating-linear-gradient(45deg, ${rgbaCss(COMMAND_ENVELOPE_RGBA.dark)} 0 2px, ${rgbaCss(COMMAND_ENVELOPE_RGBA.light)} 2px 3.5px, transparent 3.5px 7px)`;

/** The legend draws the markers a little closer than the map does, so their symbols stay readable at 30 px. */
const LEGEND_ITEM_VIEWBOX = "-20 -20 40 40";
const LEGEND_RECORD_VIEWBOX = "-16 -23 37 37";
const glyph = (kind: "call" | "report", urgency: ExerciseUrgency, status: "new" | "assigned" | "done" = "new") =>
  <MarkerGlyph nodes={exerciseMarkerNodes(exerciseMarkerSpec({ kind, urgency }, status))} viewBox={LEGEND_ITEM_VIEWBOX} size={30} />;

/** The three parts of the legend: what the map draws of the model, the reports of 2024, and the exercise. */
export type CommandLegendTab = "map" | "reports" | "exercise";
export const COMMAND_LEGEND_TABS: readonly CommandLegendTab[] = ["map", "reports", "exercise"];
const LEGEND_TAB_LABEL: Readonly<Record<CommandLegendTab, Localized>> = { map: COMMAND_LEGEND.tabMap, reports: COMMAND_LEGEND.tabReports, exercise: COMMAND_LEGEND.tabExercise };

/**
 * The legend chip, and the open legend. The open legend has three short parts, one on screen at a time, so nothing is
 * cut and nothing scrolls: the map (water, roads and places of the model), the reports (place records of 2024 and
 * the marks that go with them), and the exercise (the marker grammar as a grid of shape by urgency, the three
 * handling states, and the staging point). The chip and the open legend never show together.
 */
export function CommandLegend({ language, open, onToggle, facilities, unmodelledRoads, wetSites, mode = "trainee", initialTab = "map", legendRef }: {
  language: Language;
  open: boolean;
  onToggle: (open: boolean) => void;
  /** Trainee mode draws a shelter that is not yet reported as an outline; hindsight mode draws the season envelope. */
  mode?: CommandMode;
  /** The key facilities are on the map. */
  facilities: boolean;
  /** The replay data holds road pieces outside the model. */
  unmodelledRoads: boolean;
  /** A reported site can be in modelled water during the replay. */
  wetSites: boolean;
  /** The part the legend opens on. */
  initialTab?: CommandLegendTab;
  legendRef?: Ref<HTMLDivElement>;
}) {
  const t = (entry: Localized) => pick(entry, language);
  const title = useId();
  const panel = useId();
  const [tab, setTab] = useState<CommandLegendTab>(initialTab);
  if (!open) {
    return (
      <button type="button" className={styles.legendChip} onClick={() => onToggle(true)} aria-expanded="false" data-region="G" data-command-legend="chip" lang={language}>
        {t(COMMAND_LEGEND.chip)}<ChevronUp size={16} aria-hidden="true" />
      </button>
    );
  }
  return (
    <div ref={legendRef} className={`${styles.panel} ${styles.legend}`} role="group" aria-labelledby={title} data-region="G" data-command-legend="open" data-clear-panel lang={language}>
      <div className={`${styles.popoverHead} ${styles.legendHead}`}>
        <h2 id={title} tabIndex={-1} data-command-panel-title>{t(COMMAND_LEGEND.title)}</h2>
        <button type="button" className={styles.iconButton} onClick={() => onToggle(false)} aria-expanded="true" aria-label={t(COMMAND_LEGEND.close)}><ChevronDown size={18} aria-hidden="true" /></button>
      </div>
      <div className={styles.legendTabs} role="tablist" aria-label={t(COMMAND_LEGEND.tabs)}>
        {COMMAND_LEGEND_TABS.map((id) => (
          <button key={id} type="button" role="tab" aria-selected={id === tab} aria-controls={panel} onClick={() => setTab(id)} data-command-legend-tab={id}>{t(LEGEND_TAB_LABEL[id])}</button>
        ))}
      </div>
      <div id={panel} role="tabpanel" className={styles.legendBody} data-legend-tab={tab}>
        {tab === "map" && (
          <>
            <div className={styles.legendTitle}>
              <h3>{t(COMMAND_LEGEND.water)}</h3>
              {/* What the map draws of water and roads is modelled: the same dashed tag as on the clock card. */}
              <span className={styles.laneTag} data-command-lane="model">{t(COMMAND_FIGURES.modelTag)}</span>
            </div>
            <ul className={styles.legendGrid} lang={language}>
              <li><i className={styles.swatch} style={{ background: rgbaCss(COMMAND_WATER_RGBA.shallow) }} />{t(COMMAND_LEGEND.shallow)}</li>
              <li><i className={styles.swatch} style={{ background: rgbaCss(COMMAND_WATER_RGBA.deep) }} />{t(COMMAND_LEGEND.deep)}</li>
              <li><i className={styles.swatch} style={{ background: `repeating-linear-gradient(135deg, ${LOW_STRIPE} 0 2px, ${LOW_WASH} 2px 6px)` }} />{t(COMMAND_LEGEND.lowConfidence)}</li>
              <li><i className={styles.swatch} style={{ background: "#e6ebf0" }} />{t(COMMAND_LEGEND.veil)}</li>
              {mode === "hindsight" && <li className={styles.legendSpan}><i className={styles.swatch} style={{ background: ENVELOPE_SAMPLE }} data-legend-envelope />{t(COMMAND_MARKERS.envelope)}</li>}
            </ul>
            <h3>{t(COMMAND_LEGEND.roads)}</h3>
            <ul className={styles.legendGrid} lang={language}>
              {/* A road is drawn as on the map: a dry one on the ground, a wet or impassable one on its white casing over modelled water. */}
              <li><span className={styles.sample}><i style={{ borderTopWidth: 1.5, borderTopColor: "#98a3a4" }} /></span>{t(COMMAND_LEGEND.roadDry)}</li>
              <li><span className={styles.sample} data-over="water" data-casing="true"><i style={{ borderTopWidth: 2.5, borderTopStyle: "dashed", borderTopColor: COMMAND_WET_ROAD }} /></span>{t(COMMAND_LEGEND.roadWet)}</li>
              <li><span className={styles.sample} data-over="water" data-casing="true"><i style={{ borderTopWidth: 3, borderTopColor: "#c62f24" }} /></span>{t(COMMAND_LEGEND.roadImpassable)}</li>
              {unmodelledRoads && <li><span className={styles.sample}><i style={{ borderTopWidth: 2, borderTopStyle: "dotted", borderTopColor: "#98a3a4" }} /></span>{t(COMMAND_LEGEND.roadUnmodelled)}</li>}
            </ul>
            <h3>{t(COMMAND_LEGEND.places)}</h3>
            <ul className={`${styles.legendGrid} ${styles.legendWide}`} lang={language}>
              <li><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d={STAR_PATH} fill="#17616e" stroke="#ffffff" strokeWidth="2" strokeLinejoin="round" paintOrder="stroke" /></svg>{t(COMMAND_LEGEND.shelter)}</li>
              {wetSites && <li><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d={STAR_PATH} fill="#ffffff" stroke="#17616e" strokeWidth="1.7" strokeLinejoin="round" /><path d="M3.5 21 20.5 3" stroke="#12262d" strokeWidth="2.4" strokeLinecap="round" /></svg>{t(COMMAND_LEGEND.shelterWet)}</li>}
              {mode === "trainee" && <li><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d={STAR_PATH} fill="#ffffff" stroke="#17616e" strokeWidth="1.5" strokeDasharray="2.6 2" strokeLinejoin="round" /></svg>{t(COMMAND_LEGEND_REPORTS.sitePending)}</li>}
              <li><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M12 2.5l9.5 9.5-9.5 9.5L2.5 12z" fill="#12262d" stroke="#ffffff" strokeWidth="2" strokeLinejoin="round" paintOrder="stroke" /></svg>{t(COMMAND_LEGEND.commandCentre)}</li>
              {facilities && <li><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><circle cx="12" cy="12" r="6" fill="#ffffff" stroke="#12262d" strokeWidth="2" /></svg>{t(COMMAND_LEGEND.facility)}</li>}
              {facilities && <li><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><circle cx="12" cy="12" r="7" fill="#2f86c4" stroke="#ffffff" strokeWidth="2" /></svg>{t(COMMAND_LEGEND.facilityWet)}</li>}
              <li><span className={styles.sample}><i style={{ borderTopWidth: 1.5, borderTopStyle: "dashed", borderTopColor: "#5f6f73" }} /></span>{t(COMMAND_LEGEND.boundary)}</li>
            </ul>
            <p className={styles.legendNote} lang={language}>{t(COMMAND_LEGEND.note)}</p>
          </>
        )}
        {tab === "reports" && (
          <>
            <h3>{t(COMMAND_LEGEND_REPORTS.records)}</h3>
            <ul className={`${styles.legendGrid} ${styles.legendWide}`} lang={language} data-legend="records">
              <li><MarkerGlyph nodes={placeRecordMarkerNodes(3, false)} viewBox={LEGEND_RECORD_VIEWBOX} size={30} />{t(COMMAND_LEGEND_REPORTS.bubble)}</li>
              <li title={t(COMMAND_MARKERS.modelDryMeaning)}><MarkerGlyph nodes={placeRecordMarkerNodes(2, true)} viewBox={LEGEND_RECORD_VIEWBOX} size={30} />{t(COMMAND_MARKERS.modelDry)}</li>
              <li><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="rgb(18 38 45 / 4%)" stroke="#12262d" strokeWidth="1.2" strokeDasharray="3 3" /></svg>{t(COMMAND_MARKERS.tolerance)}</li>
            </ul>
            <h3>{t(COMMAND_LEGEND_REPORTS.other)}</h3>
            <ul className={`${styles.legendGrid} ${styles.legendWide}`} lang={language} data-legend="other">
              <li><ClusterGlyph records={11} items={7} lifeAtRisk={2} />{t(COMMAND_LEGEND_REPORTS.cluster)}</li>
              <li title={t(COMMAND_MARKERS.noReportsMeaning)}>
                <span className={styles.legendPair}><NoReportsGlyph size={16} /><span className={styles.legendNoReports} lang={language}>{t(COMMAND_MARKERS.noReports)}</span></span>
                {t(COMMAND_LEGEND_REPORTS.noReports)}
              </li>
              <li><span className={styles.legendSign} lang={language}>{commandDeviceSign(2, language)}</span>{t(COMMAND_LEGEND_REPORTS.device)}</li>
            </ul>
            {/* The time bar: its marks are the rows of "Known by now", and the grey bars under the phases are the rain. */}
            <h3>{t(COMMAND_LEGEND.timebar)}</h3>
            <ul className={`${styles.legendGrid} ${styles.legendWide}`} lang={language} data-legend="timebar">
              <li><span className={styles.legendMark}><i data-filled="true" /></span>{t(COMMAND_LEGEND.markFilled)}</li>
              <li><span className={styles.legendMark}><i data-filled="false" /></span>{t(COMMAND_LEGEND.markHollow)}</li>
              <li><span className={styles.legendMark}><i data-filled="true" data-count="3">3</i></span>{t(COMMAND_LEGEND.markCount)}</li>
              <li><span className={styles.legendRain}><i style={{ height: 5 }} /><i style={{ height: 13 }} /><i style={{ height: 8 }} /><i style={{ height: 3 }} /></span>{t(COMMAND_LEGEND.rainBars)}</li>
            </ul>
          </>
        )}
        {tab === "exercise" && (
          <>
            <h3>{t(COMMAND_LEGEND_REPORTS.exercise)}</h3>
            {/* The marker grammar as a grid: the shape says the kind, and symbol, size and colour together say the urgency. */}
            <table className={styles.legendMatrix} data-legend="exercise">
              <thead>
                <tr>
                  <td />
                  {EXERCISE_URGENCIES.map((urgency) => <th key={urgency} scope="col">{t(COMMAND_URGENCY[urgency])}</th>)}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">{t(COMMAND_LEGEND_REPORTS.rowCall)}</th>
                  {EXERCISE_URGENCIES.map((urgency) => <td key={urgency}>{glyph("call", urgency)}</td>)}
                </tr>
                <tr>
                  <th scope="row">{t(COMMAND_LEGEND_REPORTS.rowReport)}</th>
                  {EXERCISE_URGENCIES.map((urgency) => <td key={urgency}>{glyph("report", urgency)}</td>)}
                </tr>
              </tbody>
            </table>
            <ul className={styles.legendStates} lang={language} data-legend="states">
              <li>{glyph("call", "urgent", "new")}<span>{t(COMMAND_LEGEND_REPORTS.stateNew)}</span></li>
              <li>{glyph("call", "urgent", "assigned")}<span>{t(COMMAND_LEGEND_REPORTS.stateSolid)}</span></li>
              <li>{glyph("call", "urgent", "done")}<span>{t(COMMAND_LEGEND_REPORTS.stateClosed)}</span></li>
            </ul>
            <ul className={`${styles.legendGrid} ${styles.legendWide}`} lang={language} data-legend="line">
              <li><span className={styles.legendPill} lang={language}><b>{t(COMMAND_EXERCISE.short)}</b><span>BOAT-2 · {commandWaitingShort(6, language)}</span></span>{t(COMMAND_LEGEND_REPORTS.waiting)}</li>
              {/* The exercise: where the team starts, and the straight line from there. A straight line is never a route. */}
              <li>
                <span className={act.stagingBadge} aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="12" height="12"><path d={STAGING_FLAG_PATH} fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
                </span>
                {t(COMMAND_NEAR.legendStaging)}
              </li>
              <li><span className={styles.sample}><i style={{ borderTopWidth: 1.6, borderTopStyle: "dashed", borderTopColor: "#12262d" }} /></span>{t(COMMAND_NEAR.legendLine)}</li>
            </ul>
            <p className={styles.legendNote} lang={language}>{t(COMMAND_LEGEND_REPORTS.urgencyRule)}</p>
          </>
        )}
      </div>
    </div>
  );
}

// --- H. Watermark and credits ------------------------------------------------------------------------------

/** The exercise label tiled across the map in both languages at once. It is drawn, not announced: the banner says it. */
export function CommandWatermark({ tiles = 120 }: { tiles?: number }) {
  return (
    <div className={styles.watermark} aria-hidden="true" data-region="H" data-command-watermark>
      <div>{Array.from({ length: tiles }, (_, index) => <span key={index}>{COMMAND_BANNER.watermark.en}</span>)}</div>
    </div>
  );
}

/** Scale bar and map credits, above the time dock. The street map and the roads are OpenStreetMap data. */
export function CommandCredits({ language, view, revision, layerCredit = null }: {
  language: Language;
  view: CommandMapView | null;
  revision: string | null;
  /** The short credit of a layer that is on the map only at times: the 2024 season envelope in hindsight mode. */
  layerCredit?: string | null;
}) {
  const bar = view ? commandScaleBar(view.metresPerPixel, 110) : null;
  return (
    <div className={styles.credits} data-command-credits aria-label={pick(COMMAND_MAP.credits, language)} role="group" lang={language}>
      {bar && bar.pixels > 0 && (
        <span className={styles.scale} data-command-scale>
          <span>{commandScaleLabel(bar.metres, language)}</span>
          <i className={styles.scaleBar} style={{ width: Math.round(bar.pixels) }} />
        </span>
      )}
      <span className={styles.creditText}>{COMMAND_CREDITS.osm} · {COMMAND_CREDITS.terrain}{layerCredit ? ` · ${layerCredit}` : ""}{revision ? ` · ${commandDataTag(revision, language)}` : ""}</span>
    </div>
  );
}

// --- I. Notice ---------------------------------------------------------------------------------------------

/**
 * One line at the top centre of the map. It says what the page did or could not do, or that an invented item of the
 * exercise has arrived; it is never a warning. With `onSelect` the line is a button that shows what it names.
 */
export function CommandNotice({ message, language, onSelect, action }: {
  message: string | null;
  language: Language;
  onSelect?: () => void;
  /**
   * A button beside the line: "Undo" after an action of the exercise (with a line under it that runs out with the ten
   * seconds), or "Cancel" while the page waits for a tap on the map. `id` restarts that line for a new action.
   */
  action?: { id: string; label: string; onPress: () => void; timed?: boolean };
}) {
  return (
    <div role="status" data-region="I" lang={language}>
      {message && (action
        ? (
          <p key={action.id} className={styles.notice} data-command-notice="with-action">
            {message}
            <button type="button" className={act.noticeAction} onClick={action.onPress} data-command-notice-action>{action.label}{action.timed && <i aria-hidden="true" />}</button>
          </p>
        )
        : onSelect
          ? <button type="button" className={styles.notice} onClick={onSelect} data-command-notice="action">{message}<ArrowRight size={14} aria-hidden="true" style={{ marginLeft: 8, marginRight: 0 }} /></button>
          : <p className={styles.notice} data-command-notice>{message}</p>)}
    </div>
  );
}
