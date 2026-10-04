"use client";

import { Component, useLayoutEffect, useRef, type ReactNode } from "react";
import { addAfterEffect, Canvas, useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { sampleStory } from "@/lib/landing/sample-story";
import { applyStoryFrame, createTerrainScene, getSceneTelemetry, type TerrainRig } from "./scene/terrain-scene";

interface ProgressStore {
  getSnapshot: () => number;
  subscribe: (listener: () => void) => () => void;
}

interface NarrativeCanvasProps {
  store: ProgressStore;
  onReady: () => void;
  onPending: () => void;
  onFailure: (reason?: string) => void;
  active: boolean;
}

class RendererBoundary extends Component<{ children: ReactNode; onFailure: (reason?: string) => void }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { this.props.onFailure("The illustrated scene could not be prepared."); }
  render() { return this.state.failed ? null : this.props.children; }
}

function Scene({ store, onReady, onPending, onFailure, active, host }: NarrativeCanvasProps & { host: React.RefObject<HTMLDivElement | null> }) {
  const { camera, gl, scene, invalidate, size } = useThree();
  const rig = useRef<TerrainRig | null>(null);
  const callbacks = useRef({ onReady, onPending, onFailure, active, width: size.width, height: size.height });
  const rendered = useRef(false);
  const frameStart = useRef(0);
  const needsReady = useRef(true);

  useLayoutEffect(() => {
    if (!active || size.width !== callbacks.current.width || size.height !== callbacks.current.height) {
      needsReady.current = true;
      onPending();
      host.current?.setAttribute("data-ready", "false");
    }
    callbacks.current = { onReady, onPending, onFailure, active, width: size.width, height: size.height };
    if (active && size.width > 0 && size.height > 0 && rig.current && camera instanceof THREE.OrthographicCamera) {
      applyStoryFrame(rig.current, camera, size.width / Math.max(1, size.height), sampleStory(store.getSnapshot()), "reading-column");
      invalidate();
    }
  }, [onReady, onPending, onFailure, active, size.width, size.height, camera, store, invalidate, host]);

  useLayoutEffect(() => {
    if (!(camera instanceof THREE.OrthographicCamera)) {
      callbacks.current.onFailure("The illustrated camera could not be prepared.");
      return;
    }
    let disposed = false;
    let frameCount = 0;
    let slowFrames = 0;
    let nextProgress = store.getSnapshot();
    const model = createTerrainScene();
    rig.current = model;
    applyStoryFrame(model, camera, Math.max(1, callbacks.current.width) / Math.max(1, callbacks.current.height), sampleStory(nextProgress), "reading-column");
    scene.add(model.world);
    const apply = () => {
      if (disposed || !callbacks.current.active || callbacks.current.width <= 0 || callbacks.current.height <= 0) return;
      nextProgress = store.getSnapshot();
      applyStoryFrame(model, camera, callbacks.current.width / Math.max(1, callbacks.current.height), sampleStory(nextProgress), "reading-column");
      invalidate();
    };
    const unsubscribe = store.subscribe(apply);
    const removeAfterEffect = addAfterEffect(() => {
      if (!rendered.current || disposed) return;
      rendered.current = false;
      frameCount += 1;
      const duration = performance.now() - frameStart.current;
      slowFrames = duration > 100 ? slowFrames + 1 : 0;
      if (host.current) {
        const telemetry = getSceneTelemetry(model, camera);
        host.current.dataset.renderFrames = String(frameCount);
        host.current.dataset.triangles = String(gl.info.render.triangles);
        host.current.dataset.drawCalls = String(gl.info.render.calls);
        host.current.dataset.sceneProgress = store.getSnapshot().toFixed(6);
        host.current.dataset.floodAmount = telemetry.floodAmount.toFixed(6);
        host.current.dataset.cameraSignature = telemetry.cameraSignature;
        host.current.dataset.landmarks = JSON.stringify(telemetry.landmarks);
        host.current.dataset.ready = "true";
      }
      if (needsReady.current && callbacks.current.active && callbacks.current.width > 0 && callbacks.current.height > 0) {
        needsReady.current = false;
        callbacks.current.onReady();
      }
      if (slowFrames >= 10) callbacks.current.onFailure("The illustrated scene is rendering slowly on this device.");
    });
    const lost = (event: Event) => {
      event.preventDefault();
      callbacks.current.onFailure("The illustrated scene lost its graphics context.");
    };
    gl.domElement.addEventListener("webglcontextlost", lost);
    apply();
    return () => {
      disposed = true;
      unsubscribe(); removeAfterEffect();
      gl.domElement.removeEventListener("webglcontextlost", lost);
      scene.remove(model.world); model.dispose(); rig.current = null;
    };
  }, [camera, gl, scene, store, invalidate, host]);

  useFrame(() => {
    rendered.current = true;
    frameStart.current = performance.now();
  });
  return null;
}

/** Optional illustration only. All narrative meaning and destinations remain in server-rendered HTML. */
export default function NarrativeCanvas(props: NarrativeCanvasProps) {
  const host = useRef<HTMLDivElement>(null);
  return (
    <div ref={host} data-narrative-canvas data-scene-active={props.active} aria-hidden="true" style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
      <RendererBoundary onFailure={props.onFailure}>
        <Canvas
          orthographic
          shadows="soft"
          frameloop="demand"
          dpr={[1, 1.5]}
          camera={{ position: [14, 19, 22], near: 0.1, far: 120, zoom: 1 }}
          gl={{ antialias: true, alpha: true, powerPreference: "low-power" }}
          onCreated={({ gl }) => {
            gl.setClearColor("#f2f6f1", 0);
            gl.toneMapping = THREE.ACESFilmicToneMapping;
            gl.toneMappingExposure = 1.08;
          }}
          fallback={null}
        >
          <Scene {...props} host={host} />
        </Canvas>
      </RendererBoundary>
    </div>
  );
}
