import type { BriefAccess, BriefIntervention, EvidenceLibraryPackage } from "@floodguard/contracts";
import styles from "./evidence-library.module.css";

const names = {
  add_destination: ["Add a temporary destination", "เพิ่มจุดหมายชั่วคราว"],
  close_edge: ["Interrupt a consequential road link", "ทดสอบการปิดช่วงถนนที่มีผลต่อการเข้าถึง"],
  remove_destination: ["Remove a destination serving demand", "ทดสอบการหยุดให้บริการจุดหมาย"],
};
const count = (value: number | null | undefined, th: boolean) => value == null ? (th ? "ยังไม่มีข้อมูล" : "Unavailable") : value.toLocaleString(th ? "th-TH" : "en-GB", { maximumFractionDigits: 1 });
const duration = (value: number | null, th: boolean) => value == null ? count(value, th) : value.toLocaleString(th ? "th-TH" : "en-GB", { maximumFractionDigits: 4, signDisplay: "exceptZero" });

function AccessContext({ access, th }: { access: BriefAccess; th: boolean }) {
  const rows: [string, number][] = [
    [th ? "ประชากรตามแบบจำลองในพื้นที่ศึกษา (ปี 2020)" : "Modelled residents in the study area (2020)", access.modelled_population],
    [th ? "เข้าถึงจุดหมายภายใน 30 นาทีตามแบบจำลอง" : "Within 30 minutes in the baseline model", access.within_30_minutes_population],
    [th ? "มีเส้นทาง แต่เกิน 30 นาที" : "A route exists, but exceeds 30 minutes", access.over_30_minutes_population],
    [th ? "เชื่อมกับถนน แต่ไม่มีเส้นทางถึงจุดหมาย" : "Connected to roads, without a route to a destination", access.connected_without_route_population],
    [th ? "ยังประเมินการเข้าถึงไม่ได้: เชื่อมกับถนนไม่สำเร็จ" : "Access unknown: no accepted connection to the road graph", access.unknown_access_population],
  ];
  return <dl className={styles.briefMetrics}>{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{count(value, th)}</dd></div>)}</dl>;
}

function Intervention({ item, th }: { item: BriefIntervention; th: boolean }) {
  return <article data-brief-intervention={item.kind}>
    <p className={styles.eyebrow}>{th ? "สถานการณ์สมมติ" : "MODEL EXPERIMENT"}</p><h3>{names[item.kind][th ? 1 : 0]}</h3>
    <dl><div><dt>{th ? "เข้าถึงภายใน 30 นาทีเพิ่มขึ้น" : "Gain access within 30 minutes"}</dt><dd>{count(item.gaining_30_min_access, th)}</dd></div><div><dt>{th ? "สูญเสียการเข้าถึงภายใน 30 นาที" : "Lose access within 30 minutes"}</dt><dd>{count(item.losing_30_min_access, th)}</dd></div><div><dt>{th ? "ใช้เวลาเดินทางนานขึ้น / สั้นลง" : "Travel becomes slower / faster"}</dt><dd>{count(item.slower_population, th)} / {count(item.faster_population, th)}</dd></div><div><dt>{th ? "เวลาเฉลี่ยเปลี่ยนแปลง (นาที)" : "Mean travel-time change (minutes)"}</dt><dd>{duration(item.mean_travel_time_delta_minutes, th)}</dd></div></dl>
    <p>{item.result === "threshold_change" ? (th ? "มีประชากรข้ามเกณฑ์ 30 นาทีในแบบจำลองนี้ ควรตรวจสอบสถานที่และเส้นทางที่ทำให้ผลเปลี่ยน" : "This experiment moves residents across the 30-minute threshold. Verify the affected connection or destination before considering an intervention.") : item.result === "travel_time_only" ? (th ? "เวลาเดินทางเปลี่ยน แต่ยังไม่มีประชากรข้ามเกณฑ์ 30 นาที" : "Travel times change even though nobody crosses the 30-minute threshold.") : (th ? "ไม่พบการเปลี่ยนแปลงที่วัดได้ในแบบจำลองนี้ ไม่ได้ยืนยันว่าการเปลี่ยนแปลงนี้ไม่มีผลในสถานการณ์จริง" : "No measured change in this model. This does not establish that the intervention has no real-world effect.")}</p>
    <p className={styles.hint}>{th ? "ค่าเฉลี่ยใช้เฉพาะประชากรที่มีเส้นทางทั้งก่อนและหลัง ไม่รวมผู้ที่ไม่มีเส้นทาง" : "The mean compares only residents with a route in both cases; newly unreachable residents are excluded from that mean."}</p>
    <details><summary>{th ? "เหตุผลการเลือกการทดสอบ" : "Why this experiment was selected"}</summary><p>{item.selection_method}</p><p>{item.scenario_id}</p></details>
  </article>;
}

export function DecisionBriefPanel({ evidence, th }: { evidence: EvidenceLibraryPackage; th: boolean }) {
  const brief = evidence.decision_brief;
  if (!brief) return <p className={styles.empty}>{th ? "ชุดข้อมูลนี้ยังไม่มีบทสรุปเพื่อการตัดสินใจ" : "A decision brief is unavailable for this package."}</p>;
  const query = new URLSearchParams({ aoi: evidence.aoi_id, event: evidence.event_id });
  return <div data-decision-brief="true">
    <section className={`${styles.panel} ${styles.briefLead}`}>
      <p className={styles.eyebrow}>{th ? "สิ่งที่ตัดสินใจได้ในขณะนี้" : "WHAT CAN BE DECIDED NOW"}</p>
      <h2>{th ? "ตรวจสอบจุดเชื่อมต่อและจุดหมายที่มีผลต่อการเข้าถึง" : "Prioritize review of consequential connections and destinations"}</h2>
      <p>{th ? "ยังจัดอันดับความเร่งด่วนของพื้นที่ไม่ได้ หลักฐานปัจจุบันช่วยเลือกสิ่งที่ควรตรวจสอบและเปรียบเทียบสถานการณ์สมมติ" : "An accepted response ranking is not yet available. The current evidence helps target verification and compare explicit interventions."}</p>
      <div className={styles.briefStats}><div><span>{th ? "คะแนน / ระดับการดำเนินการ" : "FPPS / action class"}</span><strong>{th ? "ยังไม่พร้อม" : "Unavailable"}</strong></div><div><span>{th ? "ประชากรที่ได้รับผลจากน้ำท่วม" : "Flood-affected population"}</span><strong>{th ? "ยังไม่ทราบ" : "Unknown"}</strong></div><div><span>{th ? "สถานะผลลัพธ์" : "Result status"}</span><strong>{th ? "สมมติฐาน / การทบทวน" : "Scenario / review"}</strong></div></div>
      <p className={styles.hint}>{th ? "ลำดับการตรวจสอบไม่ใช่ลำดับการอพยพหรือคำสั่งปฏิบัติการ" : "Review priority is not an evacuation priority or an operational instruction."}</p>
    </section>
    <section className={styles.panel}><h2>{th ? "ประชากรและช่องว่างการเข้าถึง" : "Population context and access gaps"}</h2>
      {brief.access ? <AccessContext access={brief.access} th={th} /> : <p className={styles.empty}>{th ? "พื้นที่นี้มีข้อมูลความครอบคลุม ยังไม่มีการคำนวณการเข้าถึง" : "This area has an evidence-coverage view; access calculations are unavailable."}</p>}
      <p>{th ? "ตัวเลขเหล่านี้เป็นประชากรที่อยู่อาศัยตามแบบจำลอง WorldPop ปี 2020 ไม่ใช่จำนวนผู้ประสบภัยหรือผู้ต้องการอพยพ การเดินทางใช้ความเร็วและจุดเชื่อมต่อตามสมมติฐาน" : "These are WorldPop 2020 modelled residents, not flood victims or evacuation demand. Travel times depend on assumed speeds and accepted graph connectors."}</p>
    </section>
    <section className={styles.panel}><h2>{th ? "การเปลี่ยนแปลงใดมีผลในแบบจำลอง" : "Which changes make a difference in the model?"}</h2>
      <p>{th ? "เปรียบเทียบแต่ละการเปลี่ยนแปลงกับกรณีฐานแยกกัน การปิดถนนและจุดหมายเป็นการทดสอบ ไม่ใช่รายงานเหตุการณ์จริง" : "Each change is compared independently with the baseline. Closures and destination availability are imposed experiments."}</p>
      <div className={styles.scenarios}>{brief.interventions.map((item) => <Intervention key={item.id} item={item} th={th} />)}</div>
      {!brief.interventions.length ? <p className={styles.empty}>{th ? "ยังไม่มีการทดลองสำหรับพื้นที่นี้" : "No intervention experiment is available for this area."}</p> : null}
    </section>
    <section className={styles.panel}><h2>{th ? "บริบทระดับตำบล" : "Subdistrict reporting context"}</h2>
      <p>{th ? "รายงานเฉพาะส่วนที่ซ้อนทับพื้นที่ศึกษา ใช้ขอบเขตอ้างอิงปี 2022 ยังไม่ยืนยันขอบเขต ณ วันเกิดเหตุ ไม่จัดอันดับตำบลจากข้อมูลที่ยังไม่ครบ" : "Only the intersection with the study area is reported. Boundaries reference 2022; event-date currency is unverified. Incomplete evidence does not support subdistrict rankings."}</p>
      {brief.reporting.status === "available" ? <div className={styles.tableWrap} tabIndex={0} role="region" aria-label={th ? "ตารางตำบล เลื่อนแนวนอนได้" : "Subdistrict context table; scroll horizontally"}><table><thead><tr><th>{th ? "ตำบล" : "Subdistrict"}</th><th>{th ? "สัดส่วนพื้นที่ตำบลใน AOI" : "Subdistrict area inside AOI"}</th><th>{th ? "ประชากรตามแบบจำลอง" : "Modelled residents"}</th><th>{th ? "การเข้าถึงยังไม่ทราบ" : "Access unknown"}</th><th>{th ? "การทดลองที่ควรทบทวน" : "Experiment to review"}</th></tr></thead><tbody>{brief.reporting.units.map((unit) => { const addition = unit.interventions.find((item) => item.kind === "add_destination"); return <tr key={unit.id}><th scope="row">{th ? unit.name_th : unit.name}<small>{unit.id}</small></th><td>{count(unit.unit_coverage_fraction * 100, th)}%<small>{unit.scope === "partial_unit" ? (th ? "บางส่วนของตำบล" : "Partial subdistrict") : (th ? "เต็มพื้นที่ตามขอบเขตนี้" : "Full unit in this boundary vintage")}</small></td><td>{count(unit.population_context?.modelled_population, th)}</td><td>{count(unit.population_context?.unknown_access_population, th)}</td><td>{addition ? `${th ? "เพิ่มจุดหมาย: เข้าถึง 30 นาทีเพิ่มขึ้น" : "Add destination: gain 30-minute access"} ${count(addition.gaining_30_min_access, th)}` : (th ? "ยังไม่มี" : "Unavailable")}</td></tr>; })}</tbody></table></div> : <p className={styles.empty}>{th ? "ยังไม่มีการเชื่อมโยงขอบเขตที่ยอมรับได้" : "An accepted reporting-boundary crosswalk is unavailable."}</p>}
      <p className={styles.hint}>{th ? "ประชากรที่ยังจับคู่ตำบลไม่ได้" : "Modelled residents without a unique subdistrict assignment"}: {count(brief.reporting.unassigned_modelled_population, th)}. {brief.reporting.source_url ? <a href={brief.reporting.source_url} target="_blank" rel="noopener noreferrer">{th ? "แหล่งข้อมูลขอบเขต" : "Boundary source and attribution"}</a> : null}</p>
    </section>
    <section className={styles.panel}><h2>{th ? "สิ่งที่ต้องยืนยันก่อนใช้ตัดสินใจ" : "What still needs confirmation"}</h2>
      <details><summary>{th ? "ผลตรวจสอบแหล่งข้อมูลและช่องว่าง" : "Source-review findings and remaining gaps"}</summary>{brief.evidence_notes.map((note, index) => <p key={index}><strong>{note.topic} · {note.status}</strong><br />{note.summary} {note.source_urls.map((url) => <a key={url} href={url} target="_blank" rel="noopener noreferrer">{th ? "แหล่งข้อมูล " : "Source "}</a>)}</p>)}</details>
      <ol>{brief.next_actions.map((action) => <li key={action.id}><strong>{th ? ({event_reference:"ขอบเขตน้ำท่วมที่ตรงเหตุการณ์",access_review:"จุดเชื่อมต่อถนนและจุดหมายที่มีผล",demand_capacity:"กลุ่มประชากรและสมมติฐานความจุ"}[action.id] ?? action.action) : action.action}</strong><p>{action.reason}</p></li>)}</ol>
      <p>{th ? "ความเท่าเทียมตามกลุ่มอายุยังประเมินไม่ได้ ความจุสถานที่จริงและความต้องการอพยพยังไม่ทราบ ดูสมมติฐานความจุและสัดส่วนผู้เข้าร่วมในคลังหลักฐาน" : "Age-group equity remains unavailable. Actual shelter capacity and evacuation demand remain unknown; the evidence library records explicit capacity and participation assumptions."}</p>
      {brief.capacity_experiments.length ? <details><summary>{th ? "การทดลองความจุและสัดส่วนผู้เข้าร่วม" : "Capacity and participation experiments"}</summary><p>{th ? "ใช้จุดหมายสมมติแยกจากการทดลองเพิ่มจุดหมายด้านบน ยังไม่ยืนยันความเหมาะสมของสถานที่หรือจำนวนผู้ต้องการอพยพ" : "The capacity site is a separate hypothetical location from the access addition above. Its suitability and actual evacuation demand are unverified."}</p><div className={styles.tableWrap} tabIndex={0} role="region" aria-label={th ? "ตารางการทดลองความจุ เลื่อนแนวนอนได้" : "Capacity experiment table; scroll horizontally"}><table><thead><tr><th>{th ? "สมมติฐาน" : "Assumption"}</th><th>{th ? "ความต้องการสมมติ" : "Assumed demand"}</th><th>{th ? "จัดสรรได้" : "Assigned"}</th><th>{th ? "จำกัดด้วยความจุ" : "Capacity-limited"}</th><th>{th ? "ไปไม่ถึง / ข้อมูลไม่ครอบคลุม" : "Unreachable / coverage excluded"}</th><th>{th ? "ไม่ทราบความจุ" : "Unknown capacity"}</th></tr></thead><tbody>{brief.capacity_experiments.map((item) => <tr key={item.id}><th scope="row">{item.title}</th><td>{count(item.assumed_demand, th)}</td><td>{count(item.assigned, th)}</td><td>{count(item.capacity_limited, th)}</td><td>{count(item.unreachable, th)} / {count(item.coverage_excluded, th)}</td><td>{count(item.unknown_capacity, th)}</td></tr>)}</tbody></table></div></details> : null}
      <a className={styles.download} href={`/studio/library/?${query}`}>{th ? "ตรวจสอบหลักฐานและสมมติฐานทั้งหมด" : "Inspect the evidence and assumptions"}</a>
    </section>
  </div>;
}
