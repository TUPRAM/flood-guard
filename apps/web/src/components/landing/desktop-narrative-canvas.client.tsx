"use client";

import { Component, useLayoutEffect, useRef, type ReactNode } from "react";
import { addAfterEffect, Canvas, useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { sampleDesktopStory } from "@/lib/landing/sample-desktop-story";
import { createDroneScene, applyDroneFrame, getDroneTelemetry } from "./scene/drone-scene";

interface DesktopCanvasProps {
  store: { getSnapshot: () => number; subscribe: (listener: () => void) => () => void };
  onReady: () => void;
  onPending: () => void;
  onFailure: (reason?: string) => void;
  active: boolean;
}

class RendererBoundary extends Component<{ children: ReactNode; onFailure: (reason?: string) => void }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { this.props.onFailure("desktop-renderer-failed"); }
  render() { return this.state.failed ? null : this.props.children; }
}

function Scene({ store, onReady, onPending, onFailure, active, host }: DesktopCanvasProps & { host: React.RefObject<HTMLDivElement | null> }) {
  const { camera, gl, scene, invalidate, size } = useThree();
  const rig = useRef<ReturnType<typeof createDroneScene> | null>(null);
  const callbacks = useRef({ onReady, onPending, onFailure, active, width: size.width, height: size.height });
  const pointer = useRef({ x: 0, y: 0, targetX: 0, targetY: 0 });
  const rendered = useRef(false);
  const frameStart = useRef(0);
  const needsReady = useRef(true);
  const renderedFrame = useRef(sampleDesktopStory(0));

  useLayoutEffect(() => {
    if (!active || size.width !== callbacks.current.width || size.height !== callbacks.current.height) {
      needsReady.current = true;
      onPending();
      host.current?.setAttribute("data-ready", "false");
    }
    callbacks.current = { onReady, onPending, onFailure, active, width: size.width, height: size.height };
    if (!active) pointer.current = { x: 0, y: 0, targetX: 0, targetY: 0 };
    if (active && size.width > 0 && size.height > 0) invalidate();
  }, [onReady, onPending, onFailure, active, size.width, size.height, invalidate, host]);

  useLayoutEffect(() => {
    if (!(camera instanceof THREE.PerspectiveCamera)) {
      callbacks.current.onFailure("desktop-camera-unavailable");
      return;
    }
    let disposed = false;
    let frameCount = 0;
    let slowFrames = 0;
    const model = createDroneScene();
    rig.current = model;
    const initial = sampleDesktopStory(store.getSnapshot());
    renderedFrame.current = initial;
    applyDroneFrame(model, camera, Math.max(1, callbacks.current.width) / Math.max(1, callbacks.current.height), { flight: initial.flight, flood: initial.flood, network: initial.network, result: initial.result, pointer: [0, 0] });
    scene.add(model.world);
    const requestFrame = () => {
      if (disposed || !callbacks.current.active || callbacks.current.width <= 0 || callbacks.current.height <= 0) return;
      invalidate();
    };
    const unsubscribe = store.subscribe(requestFrame);
    const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)");
    const resetPointer = () => {
      pointer.current.targetX = 0;
      pointer.current.targetY = 0;
      requestFrame();
    };
    const movePointer = (event: PointerEvent) => {
      if (!callbacks.current.active || !finePointer.matches || event.pointerType !== "mouse"
        || sampleDesktopStory(store.getSnapshot()).flight >= 1) return;
      pointer.current.targetX = Math.max(-1, Math.min(1, event.clientX / Math.max(1, window.innerWidth) * 2 - 1));
      pointer.current.targetY = Math.max(-1, Math.min(1, event.clientY / Math.max(1, window.innerHeight) * 2 - 1));
      requestFrame();
    };
    const leavePointer = (event: PointerEvent) => { if (event.relatedTarget === null) resetPointer(); };
    window.addEventListener("pointermove", movePointer, { passive: true });
    window.addEventListener("pointerout", leavePointer, { passive: true });
    window.addEventListener("blur", resetPointer);
    finePointer.addEventListener("change", resetPointer);
    const removeAfterEffect = addAfterEffect(() => {
      if (!rendered.current || disposed) return;
      rendered.current = false;
      frameCount += 1;
      slowFrames = performance.now() - frameStart.current > 100 ? slowFrames + 1 : 0;
      const element = host.current;
      if (element) {
        const telemetry = getDroneTelemetry(model, camera);
        element.dataset.renderFrames = String(frameCount);
        element.dataset.triangles = String(gl.info.render.triangles);
        element.dataset.drawCalls = String(gl.info.render.calls);
        element.dataset.sceneProgress = renderedFrame.current.progress.toFixed(6);
        element.dataset.flight = telemetry.flight.toFixed(6);
        element.dataset.floodAmount = telemetry.floodAmount.toFixed(6);
        element.dataset.networkAmount = telemetry.networkAmount.toFixed(6);
        element.dataset.resultAmount = telemetry.resultAmount.toFixed(6);
        element.dataset.waterHeight = telemetry.waterHeight.toFixed(6);
        element.dataset.cameraSignature = telemetry.cameraSignature;
        element.dataset.landmarks = JSON.stringify(telemetry.landmarks);
        element.dataset.annotations = JSON.stringify(telemetry.annotations);
        element.dataset.baselineReachable = String(telemetry.baselineReachable);
        element.dataset.scenarioReachable = String(telemetry.scenarioReachable);
        element.dataset.worldId = telemetry.worldId;
        element.dataset.pointer = JSON.stringify([pointer.current.x * (1 - renderedFrame.current.flight), pointer.current.y * (1 - renderedFrame.current.flight)]);
        element.dataset.pointerSettled = String(pointer.current.x === pointer.current.targetX && pointer.current.y === pointer.current.targetY);
        element.dataset.ready = "true";
        const story = element.closest<HTMLElement>("[data-story]");
        for (const [name, point] of Object.entries(telemetry.annotations)) {
          const label = name === "affectedLink" ? "affected-link" : name;
          story?.style.setProperty(`--annotation-${label}-x`, `${(point.x * 100).toFixed(4)}%`);
          story?.style.setProperty(`--annotation-${label}-y`, `${(point.y * 100).toFixed(4)}%`);
        }
        if (story) story.dataset.annotationReady = "true";
      }
      if (needsReady.current && callbacks.current.active && callbacks.current.width > 0 && callbacks.current.height > 0) {
        needsReady.current = false;
        callbacks.current.onReady();
      }
      if (slowFrames >= 10) callbacks.current.onFailure("desktop-renderer-too-slow");
    });
    const lost = (event: Event) => {
      event.preventDefault();
      callbacks.current.onFailure("desktop-context-lost");
    };
    gl.domElement.addEventListener("webglcontextlost", lost);
    requestFrame();
    return () => {
      disposed = true;
      unsubscribe();
      removeAfterEffect();
      window.removeEventListener("pointermove", movePointer);
      window.removeEventListener("pointerout", leavePointer);
      window.removeEventListener("blur", resetPointer);
      finePointer.removeEventListener("change", resetPointer);
      gl.domElement.removeEventListener("webglcontextlost", lost);
      scene.remove(model.world);
      model.dispose();
      rig.current = null;
    };
  }, [camera, gl, scene, store, invalidate, host]);

  useFrame((_, delta) => {
    frameStart.current = performance.now();
    rendered.current = true;
    if (!rig.current || !(camera instanceof THREE.PerspectiveCamera)) return;
    const frame = sampleDesktopStory(store.getSnapshot());
    renderedFrame.current = frame;
    const motion = pointer.current;
    if (!callbacks.current.active || frame.flight >= 1) {
      motion.x = motion.y = motion.targetX = motion.targetY = 0;
    } else {
      const ease = 1 - Math.exp(-Math.min(delta, 0.1) * 14);
      motion.x += (motion.targetX - motion.x) * ease;
      motion.y += (motion.targetY - motion.y) * ease;
      if (Math.abs(motion.targetX - motion.x) < 0.0001 && Math.abs(motion.targetY - motion.y) < 0.0001) {
        motion.x = motion.targetX;
        motion.y = motion.targetY;
      } else invalidate();
    }
    applyDroneFrame(rig.current, camera, Math.max(1, size.width) / Math.max(1, size.height), {
      flight: frame.flight, flood: frame.flood, network: frame.network, result: frame.result,
      pointer: [motion.x * (1 - frame.flight), motion.y * (1 - frame.flight)],
    });
  });
  return null;
}

/** The desktop world is optional; the complete semantic story remains server-rendered. */
export default function DesktopNarrativeCanvas(props: DesktopCanvasProps) {
  const host = useRef<HTMLDivElement>(null);
  return <div ref={host} data-narrative-canvas data-desktop-canvas data-scene-active={props.active} aria-hidden="true" style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
    <RendererBoundary onFailure={props.onFailure}>
      <Canvas frameloop="demand" shadows="soft" dpr={[1, 1.5]} camera={{ position: [0, 20, 30], fov: 34, near: 0.1, far: 500 }} gl={{ antialias: true, alpha: true, powerPreference: "low-power" }} onCreated={({ gl }) => {
        gl.setClearColor("#f5f6f2", 0);
        gl.toneMapping = THREE.ACESFilmicToneMapping;
        gl.toneMappingExposure = 1.02;
      }} fallback={null}>
        <Scene {...props} host={host} />
      </Canvas>
    </RendererBoundary>
  </div>;
}
