import type { Language } from "./types";

export function formatSourceTime(value: string, language: Language): string {
  return new Intl.DateTimeFormat(language === "th" ? "th-TH" : "en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Bangkok",
  }).format(new Date(value));
}

export function formatNumber(value: number | null, language: Language, digits = 0): string {
  if (value === null || Number.isNaN(value)) return language === "th" ? "ไม่มีข้อมูล" : "Unavailable";
  return new Intl.NumberFormat(language === "th" ? "th-TH" : "en-GB", {
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatConfidence(value: string, language: Language): string {
  if (language === "en") return value;
  return {
    high: "สูง",
    medium: "ปานกลาง",
    low: "ต่ำ",
    unknown: "ไม่ทราบ",
  }[value.toLowerCase()] ?? value;
}

export function formatTopReason(actionClass: string, value: string, language: Language): string {
  if (language === "en") return value;
  return {
    A: "การสัมผัสและการสูญเสียการเข้าถึงอยู่ในระดับสูง จึงควรตรวจสอบทรัพยากรเพื่อความปลอดภัยของชีวิตก่อน",
    B: "ความเสี่ยงของเส้นทางสำคัญและช่องว่างการเข้าถึงสูง จึงควรตรวจสอบความต่อเนื่องของการเดินทาง",
    C: "การสัมผัสและช่องว่างการเข้าถึงอาจกระทบบริการจำเป็น จึงควรตรวจสอบแผนสำรอง",
    D: "โอกาสน้ำท่วมเป็นตัวขับเคลื่อนหลัก แต่เหมาะกับมาตรการเสริมความยืดหยุ่นระยะยาว",
    E: "ควรติดตามและตรวจสอบเพิ่มเติม เพราะความเชื่อมั่นของหลักฐานยังต่ำ",
  }[actionClass] ?? value;
}
