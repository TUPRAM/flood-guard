import { describe, expect, it } from "vitest";
import { registerCameraTriangle } from "./neighborhood";
import manifest from "../../../public/landing/floodguard-v2/scene-manifest.json";

describe("projected camera registration", () => {
  it("preserves an unchanged camera without moving its artwork", () => {
    const triangle = [[100, 80], [900, 100], [450, 700]];
    expect(registerCameraTriangle(triangle, triangle)).toEqual([1, 0, 0, 1, 0, 0]);
  });

  it("aligns both native camera projections to the same intermediate ground points", () => {
    for (let index = 0; index < manifest.cameraFrames.length - 1; index++) {
      const source = manifest.cameraFrames[index].projection;
      const next = manifest.cameraFrames[index + 1].projection;
      const target = source.map((point, i) => point.map((value, axis) => (value + next[i][axis]) / 2));
      for (const triangle of [source, next]) {
        const [a, b, c, d, x, y] = registerCameraTriangle(triangle, target);
        triangle.forEach(([px, py], i) => {
          expect(a * px + c * py + x).toBeCloseTo(target[i][0], 8);
          expect(b * px + d * py + y).toBeCloseTo(target[i][1], 8);
        });
      }
    }
  });

  it("rejects collinear registration points", () => {
    const line = [[0, 0], [1, 1], [2, 2]];
    expect(() => registerCameraTriangle(line, line)).toThrow(RangeError);
  });
});
