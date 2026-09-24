/** A road graph is not a separately qualified main-road access service. */
export function MainRoadStatus({ th }: { th: boolean }) {
  return <p data-main-road-access="unavailable">{th
    ? "การเข้าถึงถนนสายหลัก: ยังไม่มีผลบริการแยกที่ผ่านการตรวจสอบ ความเชื่อมต่อในโครงข่ายถนนไม่ยืนยันสภาพหรือการเข้าถึงถนนสายหลักจริง"
    : "Main-road access: unavailable as a separate qualified service result. Road-graph connectivity does not establish real main-road access or passability."}</p>;
}
