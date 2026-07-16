import Image from "next/image";

export default function SurfaceChooser() {
  return <main className="surface-chooser" id="main-content"><div className="chooser-brand"><Image src="/icon.svg" width={74} height={74} alt="" priority /><div><p className="eyebrow">FloodGuard Thailand</p><h1>Choose a planning surface</h1><p>เลือกหน้าจอสำหรับการเตรียมพร้อมและการวางแผน</p></div></div><div className="surface-grid"><a href="/public/"><span>01</span><b>Public preparedness</b><small>Mobile-first · Thai default</small></a><a href="/command/"><span>02</span><b>Planning command center</b><small>Map-first · Desktop and tablet</small></a><a href="/studio/"><span>03</span><b>Research studio</b><small>Gates · Models · Validation</small></a></div><p className="chooser-warning">Fixture demo · Non-operational · Not an official warning</p></main>;
}
