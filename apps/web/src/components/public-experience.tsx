"use client";

import Image from "next/image";
import { useCallback, useState } from "react";

import { EvidenceNotice } from "@/components/evidence-notice";
import { GeoMap } from "@/components/geo-map";
import { LanguageToggle } from "@/components/language-toggle";
import { StatusBar } from "@/components/status-bar";
import { formatConfidence, formatNumber, formatTopReason } from "@/lib/format";
import { useFloodGuardData } from "@/lib/use-floodguard-data";
import { useLanguage } from "@/lib/use-language";

type PublicTab = "home" | "map" | "shelters" | "prepare" | "data";

const TAB_LABELS: Record<PublicTab, { th: string; en: string; icon: string }> = {
  home: { th: "หน้าแรก", en: "Home", icon: "⌂" },
  map: { th: "แผนที่", en: "Map", icon: "⌖" },
  shelters: { th: "ที่พักพิง", en: "Shelters", icon: "▱" },
  prepare: { th: "เตรียมพร้อม", en: "Prepare", icon: "✓" },
  data: { th: "ข้อมูล", en: "Data", icon: "i" },
};

const PREPAREDNESS_ITEMS = [
  { th: "บันทึกหมายเลข ปภ. 1784 และการแพทย์ฉุกเฉิน 1669", en: "Save DDPM 1784 and medical emergency 1669" },
  { th: "เตรียมยา เอกสาร และไฟฉายไว้ในถุงกันน้ำ", en: "Pack medicines, documents, and a torch in a waterproof bag" },
  { th: "วางแผนช่วยเด็ก ผู้สูงอายุ ผู้พิการ และสัตว์เลี้ยง", en: "Plan support for children, older adults, disabled people, and pets" },
  { th: "ฝึกเส้นทางหลายทางกับครอบครัว โดยยืนยันกับท้องถิ่น", en: "Rehearse more than one route and confirm locally" },
  { th: "ติดตามประกาศทางการ ไม่ใช้หน้าจอสาธิตเป็นคำสั่ง", en: "Follow official notices; never treat this demo as an order" },
] as const;

export function PublicExperience() {
  const data = useFloodGuardData();
  const [language, setLanguage] = useLanguage("th");
  const [tab, setTab] = useState<PublicTab>("home");
  const [selectedId, setSelectedId] = useState("FG-TB-002");
  const th = language === "th";
  const selected = data.areas.find((area) => area.area_id === selectedId) ?? data.areas[0];
  const selectArea = useCallback((areaId: string) => setSelectedId(areaId), []);
  const datasetLabel = data.status.dataset_mode === "fixture_demo"
    ? (th ? "ชุดข้อมูลสาธิต" : "fixture data")
    : data.status.dataset_mode === "candidate"
      ? (th ? "ข้อมูลผู้สมัคร" : "candidate data")
      : (th ? "ข้อมูลนำเข้าทางการ" : "official input");
  const hasDecisionEligibleModel = data.model_runs.some((run) => run.can_feed_decision_layer);

  return (
    <main className="public-page" lang={language}>
      <header className="public-header">
        <a href="/public/" className="brand" aria-label="FloodGuard Thailand public preparedness">
          <Image src="/icon.svg" alt="" width={42} height={42} priority />
          <span><b>FloodGuard</b><small>{th ? "การเตรียมพร้อมของประชาชน" : "Public preparedness"}</small></span>
        </a>
        <LanguageToggle language={language} onChange={setLanguage} />
      </header>

      <StatusBar data={data} language={language} compact />

      <section className="public-content" id="public-active-panel" role="tabpanel" aria-labelledby={`public-tab-${tab}`} aria-live="polite">
        {tab === "home" && (
          <>
            <section className="hero-status card">
              <div>
                <p className="eyebrow">{th ? `พื้นที่ที่เลือก · ${datasetLabel}` : `Selected area · ${datasetLabel}`}</p>
                <h1>{th ? selected.area_name_th : selected.area_name_en}</h1>
                <p>{th ? "ภาพรวมเพื่อฝึกวางแผน ไม่ใช่สถานการณ์ปัจจุบัน" : "A planning rehearsal view, not current conditions."}</p>
              </div>
              <div className={`class-orb class-${selected.action_class.toLowerCase()}`} aria-label={`${th ? "ชั้น" : "Class"} ${selected.action_class}`}>
                <span>{selected.action_class}</span><small>{th ? "ลำดับสาธิต" : "fixture class"}</small>
              </div>
            </section>

            <section className="area-picker card">
              <div className="section-heading"><div><p className="eyebrow">{th ? "เลือกพื้นที่" : "Choose an area"}</p><h2>{th ? `${data.areas.length} พื้นที่ในชุดข้อมูล` : `${data.areas.length} dataset areas`}</h2></div></div>
              <div className="area-chip-row">
                {data.areas.map((area) => (
                  <button key={area.area_id} type="button" className={area.area_id === selected.area_id ? "selected" : ""} onClick={() => setSelectedId(area.area_id)}>
                    <b>{area.action_class}</b><span>{th ? area.area_name_th : area.area_name_en}</span>
                  </button>
                ))}
              </div>
            </section>

            <section className="public-grid">
              <article className="card priority-card">
                <p className="eyebrow">{th ? "เหตุผลจากแบบจำลอง" : "Modelled reason"}</p>
                <h2>{th ? "ควรตรวจสอบข้อมูลในพื้นที่" : "Evidence to verify"}</h2>
                <p>{formatTopReason(selected.action_class, selected.top_reason, language)}</p>
                <dl className="mini-metrics">
                  <div><dt>FPPS</dt><dd>{selected.fpps_0_100.toFixed(1)}</dd></div>
                  <div><dt>{th ? "การเข้าถึง 30 นาที" : "30-min access loss"}</dt><dd>{formatNumber(selected.people_losing_30_min_access, language)} <small>{th ? `คน · ${datasetLabel}` : `people · ${datasetLabel}`}</small></dd></div>
                  <div><dt>{th ? "ความเชื่อมั่น" : "Confidence"}</dt><dd>{formatConfidence(selected.confidence_class, language)}</dd></div>
                </dl>
              </article>

              <article className="card official-guidance-card">
                <p className="eyebrow">{th ? "คำแนะนำที่เชื่อถือได้" : "Authoritative guidance"}</p>
                <h2>{th ? "ติดตามหน่วยงานทางการ" : "Follow official authorities"}</h2>
                <p>{th ? "FloodGuard ไม่ออกคำสั่งอพยพ โปรดติดตาม ปภ. กรมอุตุนิยมวิทยา และหน่วยงานท้องถิ่น" : "FloodGuard does not issue evacuation orders. Follow DDPM, TMD, and local authorities."}</p>
                <a className="primary-link" href="https://www.disaster.go.th/home" target="_blank" rel="noreferrer">{th ? "เว็บไซต์ ปภ. อย่างเป็นทางการ ↗" : "Official DDPM website ↗"}</a>
              </article>
            </section>

            <section className="card hotline-card">
              <div className="section-heading"><div><p className="eyebrow">{th ? "หมายเลขทางการ" : "Official contacts"}</p><h2>{th ? "โทรเมื่อจำเป็น" : "Call when appropriate"}</h2></div></div>
              <div className="hotline-list">
                {data.hotlines.map((hotline) => (
                  <div key={hotline.number}>
                    <span><b>{hotline.number}</b><small>{th ? hotline.label_th : hotline.label_en}</small></span>
                    <a href={hotline.href} aria-label={`${th ? "โทร" : "Call"} ${hotline.number}`}>{th ? "โทร" : "Call"}</a>
                  </div>
                ))}
              </div>
            </section>
          </>
        )}

        {tab === "map" && (
          <section className="public-map-view">
            <div className="section-heading"><div><p className="eyebrow">{th ? `แผนที่ GeoJSON · ${datasetLabel}` : `GeoJSON map · ${datasetLabel}`}</p><h1>{th ? "ภาพรวมพื้นที่เพื่อการฝึกซ้อม" : "Area planning rehearsal"}</h1></div></div>
            <GeoMap areas={data.areas} selectedId={selected.area_id} onSelect={selectArea} language={language} showRoads={false} height="390px" areaFeatures={data.areaFeatures} roadFeatures={data.roadFeatures} datasetMode={data.status.dataset_mode} />
            <EvidenceNotice tone="caution" title={th ? "เส้นทางใช้เพื่อการซ้อมเตรียมพร้อมเท่านั้น" : "Routes are for preparedness rehearsal only"}>
              {th ? "ชุดข้อมูลนี้ไม่คำนวณเส้นทางปลอดภัยและไม่แสดงการปิดถนนแบบสด" : "This dataset does not calculate a safe route or show live road closures."}
            </EvidenceNotice>
          </section>
        )}

        {tab === "shelters" && (
          <section>
            <div className="section-heading"><div><p className="eyebrow">{th ? "จุดพักพิง" : "Shelters"}</p><h1>{th ? "ตรวจสอบกับหน่วยงานท้องถิ่นก่อนเดินทาง" : "Confirm locally before travelling"}</h1></div></div>
            {data.shelters.map((shelter) => (
              <article className="card shelter-card" key={shelter.facility_id}>
                <div className="shelter-icon" aria-hidden="true">⌂</div>
                <div><p className="eyebrow">{shelter.facility_id}</p><h2>{th ? shelter.name_th : shelter.name_en}</h2><p>{th ? "ความจุและสถานะยังไม่ได้รับการยืนยัน" : "Capacity and current status are not confirmed."}</p></div>
                <span className="unconfirmed">{th ? "ไม่ยืนยัน" : "Unconfirmed"}</span>
              </article>
            ))}
            <article className="card neutral-note"><h2>{th ? "เหตุใดจึงไม่มีจำนวนที่ว่าง?" : "Why no availability count?"}</h2><p>{data.shelters.length > 0 ? (th ? "ข้อมูลสถานที่ไม่มีสัญญาความจุพร้อมเวลา จึงไม่สร้างจำนวนที่ว่างขึ้นเอง" : "The facility data has no time-stamped capacity contract, so the app does not invent availability.") : (th ? "ชุดข้อมูลปัจจุบันไม่มีรายการสถานที่พักพิงที่ผ่านสัญญาข้อมูล" : "The current dataset provides no shelter records that pass the data contract.")}</p></article>
          </section>
        )}

        {tab === "prepare" && (
          <section>
            <div className="section-heading"><div><p className="eyebrow">{th ? "รายการเตรียมพร้อม" : "Preparedness checklist"}</p><h1>{th ? "วางแผนก่อนฤดูน้ำหลาก" : "Plan before flood season"}</h1></div></div>
            <div className="checklist-grid">
              {PREPAREDNESS_ITEMS.map((item, index) => <label className="check-item" key={item.en}><input type="checkbox" /><span><b>{String(index + 1).padStart(2, "0")}</b>{item[language]}</span></label>)}
            </div>
          </section>
        )}

        {tab === "data" && (
          <section>
            <div className="section-heading"><div><p className="eyebrow">{th ? "เกี่ยวกับข้อมูล" : "About the data"}</p><h1>{th ? "สิ่งที่หน้าจอนี้ทำได้และทำไม่ได้" : "What this screen can and cannot do"}</h1></div></div>
            <div className="about-grid">
              <article className="card"><h2>{th ? "ทำได้" : "What it demonstrates"}</h2><ul><li>{th ? "อ่าน GeoJSON ที่ผ่านสัญญาข้อมูลตามสถานะที่แสดง" : "Reads schema-governed GeoJSON with its visible data state"}</li><li>{th ? "แสดงคะแนน FPPS และเหตุผลจากเอนจินที่ทดสอบแล้ว" : "Shows FPPS and reasons from the tested engine"}</li><li>{th ? "เก็บสำเนาสาธิตที่มีป้ายกำกับไว้ใช้ออฟไลน์" : "Keeps a labelled fixture snapshot for offline judging"}</li></ul></article>
              <article className="card blocked-card"><h2>{th ? "ยังทำไม่ได้" : "What remains unavailable"}</h2><ul><li>{th ? "การเตือนภัยหรือการนำทางอพยพแบบสด" : "Live warning or evacuation navigation"}</li><li>{th ? "สถานะถนนและที่พักพิงที่ยืนยันแล้ว" : "Verified live road or shelter status"}</li><li>{hasDecisionEligibleModel ? (th ? "สถานะผ่านเกณฑ์ของแบบจำลองไม่เปลี่ยนหน้าจอนี้เป็นคำสั่งฉุกเฉิน" : "Model eligibility does not turn this screen into emergency direction") : (th ? "ยังไม่มีแบบจำลองที่ผ่านเกณฑ์เพื่อส่งต่อชั้นการตัดสินใจ" : "No model run is cleared to feed the decision layer")}</li></ul></article>
            </div>
            <article className="card method-card"><h2>{th ? "วิธีวิเคราะห์การเข้าถึง" : "Access method"}</h2><p>{th ? "เอนจินปัจจุบันเปรียบเทียบเวลาเดินทางสั้นที่สุดไปยังสถานที่ที่ใกล้ที่สุดภายใต้เครือข่ายปกติและเครือข่ายที่ถูกรบกวน ที่เกณฑ์ 15/30/60 นาที ไม่ใช่ 2SFCA ที่คำนึงถึงความจุ" : "The current engine compares shortest travel time to the nearest selected facility under normal and disrupted networks at 15/30/60-minute thresholds. It is not capacity-aware 2SFCA."}</p></article>
            <p className="technical-link"><a href="/studio/">{th ? "เปิดพื้นที่วิจัยและแบบจำลอง →" : "Open the research and model studio →"}</a></p>
          </section>
        )}
      </section>

      <nav className="public-bottom-nav" aria-label={th ? "เมนูหลัก" : "Primary navigation"} role="tablist">
        {(Object.keys(TAB_LABELS) as PublicTab[]).map((key) => (
          <button key={key} id={`public-tab-${key}`} type="button" role="tab" aria-controls="public-active-panel" aria-selected={tab === key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>
            <span aria-hidden="true">{TAB_LABELS[key].icon}</span><small>{TAB_LABELS[key][language]}</small>
          </button>
        ))}
      </nav>
    </main>
  );
}
