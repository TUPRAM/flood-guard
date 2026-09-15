"use client";

import { useId, useState, type CSSProperties } from "react";
import { geometry, openingPlateSource, pathFromPoints, plateSource, plateSrcSet, plateSizes, story, type Crop, type Point, type Scene } from "@/lib/landing-v1/story";
import styles from "./landing.module.css";
import { DeferredArtwork } from "./deferred-artwork";

const route = geometry.route.map(([x, y]): Point => [x, y]);
const affectedPath = pathFromPoints(route.slice(geometry.affectedSegment.startIndex, geometry.affectedSegment.endIndex + 1));
const native = geometry.nativeSize;
const position = (point: Point): CSSProperties => ({ left: `${point[0] / native.width * 100}%`, top: `${point[1] / native.height * 100}%` });
function cropVariables(crop: Crop, prefix: string) {
  const [x, y, width, height] = crop;
  return { [`--${prefix}-ratio`]: `${width} / ${height}`, [`--${prefix}-width`]: `${native.width / width * 100}%`, [`--${prefix}-height`]: `${native.height / height * 100}%`, [`--${prefix}-left`]: `${-x / width * 100}%`, [`--${prefix}-top`]: `${-y / height * 100}%` };
}

export function StoryPlate({ scene, eager = false, onInspect }: { scene: Scene; eager?: boolean; onInspect?: (kind: "observation" | "finding") => void }) {
  const id = useId();
  const [failedSource, setFailedSource] = useState("");
  const hero = scene.id === "H-01";
  const src = hero ? openingPlateSource : plateSource(scene.waterState);
  const failed = failedSource === src;
  const affected = scene.route === "affected";
  const labels = geometry.labelAnchors;
  const crops = { ...cropVariables(hero ? geometry.viewports.hero : geometry.viewports.desktop, "plate"), ...cropVariables(hero ? geometry.viewports.heroMobile : geometry.viewports.mobile, "mobile-plate") } as CSSProperties;
  return <figure className={`${styles.plate} ${hero ? styles.heroPlate : ""}`} aria-describedby={`${id}-description`} data-fg-water={scene.waterState} data-fg-artwork="same-world-v2" style={crops}>
    <div className={styles.plateCrop} data-fg-crop={hero ? "hero" : "registered"}>
      {failed ? <div className={styles.imageFallback} role="img" aria-label={scene.imageDescription}>
        <span>Illustration unavailable</span><p>{scene.imageDescription}</p>
      </div> : <div className={styles.platePlane}>
        <DeferredArtwork data-fg-plate-image src={src} srcSet={hero ? `${src} ${native.width}w` : plateSrcSet(scene.waterState)} sizes={hero ? "100vw" : plateSizes} width={native.width} height={native.height} alt="" eager={eager} fetchPriority={hero ? "high" : undefined} decoding="async" onError={() => setFailedSource(src)} />
        {!hero && <><svg className={styles.overlay} viewBox={`0 0 ${native.width} ${native.height}`} aria-hidden="true" focusable="false">
          {scene.selection && <path d={geometry.selectedAreaPath} className={styles.selection} vectorEffect="non-scaling-stroke" />}
          {scene.route !== "none" && <>
            <path d={pathFromPoints(route)} className={styles.routeHalo} vectorEffect="non-scaling-stroke" />
            <path d={pathFromPoints(route)} className={styles.route} vectorEffect="non-scaling-stroke" />
            {affected && <>
              <path d={affectedPath} className={styles.affectedHalo} vectorEffect="non-scaling-stroke" />
              <path d={affectedPath} className={styles.affected} vectorEffect="non-scaling-stroke" />
            </>}
            {[geometry.points.homeGate, geometry.points.clinicEntrance].map(([x, y], index) => <circle key={index} cx={x} cy={y} r="11" className={styles.endpoint} vectorEffect="non-scaling-stroke" />)}
            {affected && <circle cx={geometry.points.affectedCenter[0]} cy={geometry.points.affectedCenter[1]} r="11" className={styles.affectedPoint} vectorEffect="non-scaling-stroke" />}
          </>}
          {scene.report && <>
            <path d={`M ${geometry.points.affectedCenter.join(" ")} L ${geometry.points.report.join(" ")}`} className={styles.reportLeader} vectorEffect="non-scaling-stroke" />
            <circle cx={geometry.points.report[0]} cy={geometry.points.report[1]} r="13" className={styles.reportPoint} vectorEffect="non-scaling-stroke" />
          </>}
        </svg>
        <span className={`${styles.mapLabel} ${styles.homeLabel}`} style={position(labels.homes)}>{story.routeLabels.homes}{affected && <small>{story.routeLabels.dryQualification}</small>}</span>
        <span className={`${styles.mapLabel} ${styles.clinicLabel}`} style={position(labels.clinic)}>{story.routeLabels.clinic}{affected && <small>{story.routeLabels.dryQualification}</small>}</span>
        {scene.route !== "none" && <span className={`${styles.mapLabel} ${affected ? styles.amberLabel : ""}`} style={position(labels.connection)}>{scene.chapter === "04" ? "Review needed" : affected ? story.routeLabels.affected : story.routeLabels.usual}</span>}
        {scene.report && <button type="button" className={`${styles.mapLabel} ${styles.reportLabel}`} style={position(labels.report)} onClick={() => onInspect?.("observation")} aria-label="Inspect sample observation DEMO-R01">{story.routeLabels.report}<small>Not verified</small></button>}
        {scene.selection && <button type="button" className={`${styles.mapLabel} ${styles.selectionLabel}`} style={position(labels.selection)} onClick={() => onInspect?.("finding")}>{story.routeLabels.selection}<span aria-hidden="true"> ↗</span></button>}</>}
      </div>}
    </div>
    {affected && <p className={styles.mobileQualification}>Homes and clinic are outside the illustrated flood.</p>}
    <p id={`${id}-description`} className={styles.srOnly}>{scene.imageDescription}{scene.selection ? ` ${geometry.selectedAreaMeaning}` : ""}{scene.report ? " Sample observation DEMO-R01 is not verified." : ""}</p>
  </figure>;
}
