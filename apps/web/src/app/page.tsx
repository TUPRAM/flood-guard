import Image from "next/image";

export default function SurfaceChooser() {
  return <main className="surface-chooser" id="main-content"><div className="chooser-brand"><Image src="/icon.svg" width={74} height={74} alt="" priority /><div><p className="eyebrow">FloodGuard Thailand</p><h1>Choose a planning surface</h1><p>เลือกหน้าจอสำหรับการเตรียมพร้อมและการวางแผน</p></div></div><div className="surface-grid"><a href="/public/"><span>01</span><b>Public preparedness</b><small>Household guidance · Thai default</small></a><a href="/command/"><span>02</span><b>Planning command center</b><small>Map intelligence · Desktop and tablet</small></a><a href="/studio/"><span>03</span><b>Research &amp; validation studio</b><small>Evidence · Models · Validation</small></a></div><p className="chooser-warning">Preparedness planning · Check current conditions with DDPM and local authorities</p></main>;
}
