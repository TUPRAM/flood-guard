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

import { ChevronDown, ChevronUp, CircleHelp, Info, Layers, LocateFixed, Map as MapIcon, Maximize2, Menu, Minimize2, Minus, Plus, Scan, Search, X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode, type Ref } from "react";

import { formatDateWithYear, lowConfidenceRgba, rgbaCss, type Language, type Localized, type TimelineManifest } from "@/lib/flood-timeline";
import {
  COMMAND_BANNER,
  COMMAND_CREDITS,
  COMMAND_DRAWER,
  COMMAND_DRAWER_NOT,
  COMMAND_DRAWER_SOURCES,
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
import { COMMAND_WATER_RGBA, commandScaleBar } from "@/lib/flood-timeline-command-map";
import { studioReplayHref } from "@/lib/flood-timeline-command-replay";
import { localizedText } from "@/lib/flood-timeline-copy";

import type { CommandBasemap, CommandFitTarget, CommandMapView } from "./mae-sai-command-map";
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
      <p className={styles.bannerText} data-command-banner>{rest.map((part) => <span key={part}>{part}</span>)}</p>
      <button ref={infoRef} type="button" className={styles.infoButton} onClick={onInfo} aria-haspopup="dialog" aria-expanded={infoOpen} aria-label={pick(COMMAND_BANNER.info, language)} title={pick(COMMAND_DRAWER.title, language)} data-command-info>
        <Info size={20} aria-hidden="true" />
      </button>
    </div>
  );
}

/** A native modal dialog: the browser keeps the focus inside it and closes it on Escape. */
function ModalDialog({ open, onClose, className, labelledBy, language, name, children }: {
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

function NavItems({ language, hour, onLanguage, onHelp }: { language: Language; hour: number; onLanguage: (language: Language) => void; onHelp: () => void }) {
  const t = (entry: Localized) => pick(entry, language);
  const other: Language = language === "th" ? "en" : "th";
  return (
    <>
      <a className={styles.navItem} href="/public/"><span>{t(COMMAND_NAV.public)}</span></a>
      <a className={styles.navItem} href={COMMAND_EXERCISE_ROUTE} aria-current="page"><span>{t(COMMAND_NAV.command)}</span></a>
      <a className={styles.navItem} href={studioReplayHref(hour, language)} title={t(COMMAND_NAV.studioHint)}><span>{t(COMMAND_NAV.studio)}</span></a>
      <span className={styles.navDivider} aria-hidden="true" />
      <button type="button" className={styles.navItem} onClick={() => onLanguage(other)} aria-label={t(COMMAND_NAV.switchLanguage)} data-command-language={other}>
        <span lang={other}>{other === "th" ? "ไทย" : "EN"}</span>
      </button>
      <button type="button" className={`${styles.navItem} ${styles.navRound}`} onClick={onHelp} aria-haspopup="dialog" aria-label={t(COMMAND_NAV.help)} title={`${t(COMMAND_NAV.help)} ( ? )`} data-command-help>
        <span><CircleHelp size={20} aria-hidden="true" /><span className={styles.navLabel}>{t(COMMAND_NAV.help)}</span></span>
      </button>
    </>
  );
}

/** The navigation pill of a desktop, and on a tablet one menu button that opens the same entries. */
export function CommandNav({ language, hour, menuOpen, onMenu, onLanguage, onHelp, basemap, onBasemap, navRef }: {
  language: Language;
  hour: number;
  menuOpen: boolean;
  onMenu: (open: boolean) => void;
  onLanguage: (language: Language) => void;
  onHelp: () => void;
  basemap: CommandBasemap;
  onBasemap: () => void;
  navRef?: Ref<HTMLElement>;
}) {
  const t = (entry: Localized) => pick(entry, language);
  return (
    <>
      <nav ref={navRef} className={styles.nav} data-region="C" data-clear-panel aria-label={t(COMMAND_NAV.label)} lang={language}>
        <NavItems language={language} hour={hour} onLanguage={onLanguage} onHelp={onHelp} />
      </nav>
      <button type="button" className={`${styles.tool} ${styles.menuButton}`} onClick={() => onMenu(!menuOpen)} aria-expanded={menuOpen} aria-label={t(COMMAND_NAV.menu)} title={t(COMMAND_NAV.menu)} data-command-menu data-clear-panel>
        {menuOpen ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
      </button>
      {menuOpen && (
        <nav className={`${styles.panel} ${styles.menu}`} aria-label={t(COMMAND_NAV.label)} lang={language} data-command-menu-panel data-clear-panel>
          <NavItems language={language} hour={hour} onLanguage={onLanguage} onHelp={() => { onMenu(false); onHelp(); }} />
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

/** The view popover: the Rescue preset (the only one built so far) and the key facilities, off until asked for. */
export function CommandViewPopover({ language, facilities, facilityCount, onFacilities, onClose, popoverRef }: {
  language: Language;
  facilities: boolean;
  facilityCount: number;
  onFacilities: (visible: boolean) => void;
  onClose: () => void;
  popoverRef?: Ref<HTMLDivElement>;
}) {
  const t = (entry: Localized) => pick(entry, language);
  const title = useId();
  return (
    <div ref={popoverRef} className={`${styles.panel} ${styles.popover}`} role="group" aria-labelledby={title} lang={language} data-command-popover="view" data-clear-panel>
      <div className={styles.popoverHead}>
        <h2 id={title}>{t(COMMAND_TOOLS.viewTitle)}</h2>
        <button type="button" className={styles.iconButton} onClick={onClose} aria-label={t(COMMAND_TOOLS.close)}><X size={18} aria-hidden="true" /></button>
      </div>
      <fieldset className={styles.choiceGroup}>
        <legend className={styles.srOnly}>{t(COMMAND_TOOLS.view)}</legend>
        <label className={styles.choice} lang={language}>
          <input type="radio" name="command-view" checked readOnly />
          <span>{t(COMMAND_TOOLS.rescue)}</span>
          <small>{t(COMMAND_TOOLS.rescueNote)}</small>
        </label>
        <label className={styles.choice} data-disabled="true" lang={language}>
          <input type="radio" name="command-view" disabled />
          <span>{t(COMMAND_TOOLS.evidence)}</span>
          <small>{t(COMMAND_TOOLS.evidenceNote)}</small>
        </label>
      </fieldset>
      <fieldset className={styles.choiceGroup}>
        <legend className={styles.srOnly}>{t(COMMAND_TOOLS.facilities)}</legend>
        <label className={styles.choice} lang={language}>
          <input type="checkbox" checked={facilities} onChange={(event) => onFacilities(event.currentTarget.checked)} data-command-facilities />
          <span>{t(COMMAND_TOOLS.facilities)} ({facilityCount})</span>
          <small>{t(COMMAND_TOOLS.facilitiesNote)}</small>
        </label>
      </fieldset>
    </div>
  );
}

// --- G. Legend ---------------------------------------------------------------------------------------------

const STAR_PATH = "M12 1.8l3.1 6.6 7.2.9-5.3 5 1.4 7.1L12 17.9l-6.4 3.5L7 14.3l-5.3-5 7.2-.9z";
const LOW_STRIPE = rgbaCss(lowConfidenceRgba(COMMAND_WATER_RGBA.shallow, true));
const LOW_WASH = rgbaCss(lowConfidenceRgba(COMMAND_WATER_RGBA.shallow, false));

/** The legend chip, and the open legend: a grid of what the map draws so far. The two never show together. */
export function CommandLegend({ language, open, onToggle, facilities, unmodelledRoads, wetSites, legendRef }: {
  language: Language;
  open: boolean;
  onToggle: (open: boolean) => void;
  /** The key facilities are on the map. */
  facilities: boolean;
  /** The replay data holds road pieces outside the model. */
  unmodelledRoads: boolean;
  /** A reported site can be in modelled water during the replay. */
  wetSites: boolean;
  legendRef?: Ref<HTMLDivElement>;
}) {
  const t = (entry: Localized) => pick(entry, language);
  const title = useId();
  if (!open) {
    return (
      <button type="button" className={styles.legendChip} onClick={() => onToggle(true)} aria-expanded="false" data-region="G" data-command-legend="chip" lang={language}>
        {t(COMMAND_LEGEND.chip)}<ChevronUp size={16} aria-hidden="true" />
      </button>
    );
  }
  return (
    <div ref={legendRef} className={`${styles.panel} ${styles.legend}`} role="group" aria-labelledby={title} data-region="G" data-command-legend="open" data-clear-panel lang={language}>
      <div className={styles.popoverHead}>
        <h2 id={title}>{t(COMMAND_LEGEND.title)}</h2>
        <button type="button" className={styles.iconButton} onClick={() => onToggle(false)} aria-expanded="true" aria-label={t(COMMAND_LEGEND.close)}><ChevronDown size={18} aria-hidden="true" /></button>
      </div>
      <h3>{t(COMMAND_LEGEND.water)}</h3>
      <ul className={styles.legendGrid} lang={language}>
        <li><i className={styles.swatch} style={{ background: rgbaCss(COMMAND_WATER_RGBA.shallow) }} />{t(COMMAND_LEGEND.shallow)}</li>
        <li><i className={styles.swatch} style={{ background: rgbaCss(COMMAND_WATER_RGBA.deep) }} />{t(COMMAND_LEGEND.deep)}</li>
        <li><i className={styles.swatch} style={{ background: `repeating-linear-gradient(135deg, ${LOW_STRIPE} 0 2px, ${LOW_WASH} 2px 6px)` }} />{t(COMMAND_LEGEND.lowConfidence)}</li>
        <li><i className={styles.swatch} style={{ background: "#cdd2d0" }} />{t(COMMAND_LEGEND.veil)}</li>
      </ul>
      <h3>{t(COMMAND_LEGEND.roads)}</h3>
      <ul className={styles.legendGrid} lang={language}>
        <li><i className={styles.swatchLine} style={{ borderTopWidth: 1.5, borderTopColor: "#98a3a4" }} />{t(COMMAND_LEGEND.roadDry)}</li>
        <li><i className={styles.swatchLine} style={{ borderTopWidth: 3, borderTopStyle: "dashed", borderTopColor: "#d98a1e" }} />{t(COMMAND_LEGEND.roadWet)}</li>
        <li><i className={styles.swatchLine} style={{ borderTopWidth: 4, borderTopColor: "#c62f24" }} />{t(COMMAND_LEGEND.roadImpassable)}</li>
        {unmodelledRoads && <li><i className={styles.swatchLine} style={{ borderTopWidth: 2, borderTopStyle: "dotted", borderTopColor: "#98a3a4" }} />{t(COMMAND_LEGEND.roadUnmodelled)}</li>}
      </ul>
      <h3>{t(COMMAND_LEGEND.places)}</h3>
      <ul className={`${styles.legendGrid} ${styles.legendWide}`} lang={language}>
        <li><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d={STAR_PATH} fill="#17616e" stroke="#ffffff" strokeWidth="1.5" strokeLinejoin="round" /></svg>{t(COMMAND_LEGEND.shelter)}</li>
        {wetSites && <li><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d={STAR_PATH} fill="#ffffff" stroke="#17616e" strokeWidth="1.7" strokeLinejoin="round" /><path d="M3.5 21 20.5 3" stroke="#12262d" strokeWidth="2.4" strokeLinecap="round" /></svg>{t(COMMAND_LEGEND.shelterWet)}</li>}
        <li><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M12 2.5l9.5 9.5-9.5 9.5L2.5 12z" fill="#12262d" stroke="#ffffff" strokeWidth="1.6" strokeLinejoin="round" /></svg>{t(COMMAND_LEGEND.commandCentre)}</li>
        {facilities && <li><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><circle cx="12" cy="12" r="6" fill="#ffffff" stroke="#12262d" strokeWidth="2" /></svg>{t(COMMAND_LEGEND.facility)}</li>}
        {facilities && <li><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><circle cx="12" cy="12" r="7" fill="#2f86c4" stroke="#ffffff" strokeWidth="2" /></svg>{t(COMMAND_LEGEND.facilityWet)}</li>}
        <li><i className={styles.swatchLine} style={{ borderTopWidth: 1.5, borderTopStyle: "dashed", borderTopColor: "#5f6f73" }} />{t(COMMAND_LEGEND.boundary)}</li>
      </ul>
      <p className={styles.legendNote} lang={language}>{t(COMMAND_LEGEND.note)}</p>
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
export function CommandCredits({ language, view, revision }: { language: Language; view: CommandMapView | null; revision: string | null }) {
  const bar = view ? commandScaleBar(view.metresPerPixel, 110) : null;
  return (
    <div className={styles.credits} data-command-credits aria-label={pick(COMMAND_MAP.credits, language)} role="group" lang={language}>
      {bar && bar.pixels > 0 && (
        <span className={styles.scale} data-command-scale>
          <span>{commandScaleLabel(bar.metres, language)}</span>
          <i className={styles.scaleBar} style={{ width: Math.round(bar.pixels) }} />
        </span>
      )}
      <span className={styles.creditText}>{COMMAND_CREDITS.osm} · {COMMAND_CREDITS.terrain}{revision ? ` · ${commandDataTag(revision, language)}` : ""}</span>
    </div>
  );
}

// --- I. Notice ---------------------------------------------------------------------------------------------

/** One line at the top centre of the map. It says what the page did or could not do; it is never a warning. */
export function CommandNotice({ message, language }: { message: string | null; language: Language }) {
  return <div role="status" data-region="I" lang={language}>{message && <p className={styles.notice} data-command-notice>{message}</p>}</div>;
}
