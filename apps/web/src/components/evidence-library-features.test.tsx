import { renderToStaticMarkup } from "react-dom/server";
import type { EvidenceLibraryLayer } from "@floodguard/contracts";
import { describe, expect, it } from "vitest";
import { EvidenceFeatureBrowser, evidenceFeaturePage } from "./evidence-library-features";

function layer(id: string, count: number): EvidenceLibraryLayer {
  return { id, title: `${id} features`, role: "Synthetic test context", dataset_id: "synthetic", availability: "available", reason: null,
    data: { type: "FeatureCollection", features: Array.from({ length: count }, (_, index) => ({ type: "Feature", properties: { id: `source-${index + 1}`, name: `Place ${index + 1}` }, geometry: { type: "Point", coordinates: [100 + index / 1000, 14] } })) } };
}

describe("mapped-feature table", () => {
  it("makes every record accessible across pages without dropping missing geometry", () => {
    const roads = layer("roads", 101);
    roads.data!.features[100].geometry = null;
    const pages = [0, 1, 2].map((page) => evidenceFeaturePage([roads], roads.id, page));
    expect(pages.map((page) => page.rows.length)).toEqual([50, 50, 1]);
    expect(pages.flatMap((page) => page.rows.map((row) => row.position))).toEqual(Array.from({ length: 101 }, (_, index) => index + 1));
    expect(pages[2].rows[0]).toMatchObject({ recordId: "roads:feature:101", sourceId: "source-101", name: "Place 101", geometryType: null, bounds: null });
    expect(pages[2]).toMatchObject({ total: 101, page: 2, pages: 3 });
    expect(evidenceFeaturePage([roads], roads.id, 999).page).toBe(2);
  });

  it("selects only the requested layer and distinguishes an empty collection from no publication", () => {
    const layers = [layer("roads", 101), layer("sites", 2), layer("empty", 0)];
    expect(evidenceFeaturePage(layers, "sites", 0).rows.map((row) => row.recordId)).toEqual(["sites:feature:1", "sites:feature:2"]);
    expect(evidenceFeaturePage(layers, "empty", 0)).toMatchObject({ total: 0, rows: [], layer: { id: "empty", data: { features: [] } } });
    expect(evidenceFeaturePage(layers, "unknown", 0)).toMatchObject({ layer: null, total: 0, rows: [] });
    const metadata = { ...layer("restricted", 0), data: undefined, availability: "metadata_only" as const };
    expect(renderToStaticMarkup(<EvidenceFeatureBrowser layers={[metadata]} th={false} />)).toContain("No vector feature records are published");
    expect(renderToStaticMarkup(<EvidenceFeatureBrowser layers={[layers[2]]} th={false} />)).toContain("contains 0 records");
    expect(renderToStaticMarkup(<EvidenceFeatureBrowser layers={[]} th={false} />)).toContain("No selected layer is available");
  });

  it("reports bounding boxes across multi-part geometry and stable IDs despite repeated source identifiers", () => {
    const collection = layer("multipart", 2);
    collection.data!.features[0].geometry = { type: "GeometryCollection", geometries: [
      { type: "LineString", coordinates: [[100.5, 13.2], [100.2, 13.6]] },
      { type: "Polygon", coordinates: [[[100, 13], [101, 13], [101, 14], [100, 13]]] },
    ] };
    collection.data!.features[1].properties = { id: "source-1", name: "Duplicate source ID" };
    const view = evidenceFeaturePage([collection], "multipart", 0);
    expect(view.rows[0].bounds).toEqual([100, 13, 101, 14]);
    expect(new Set(view.rows.map((row) => row.recordId)).size).toBe(2);
  });

  it("provides labeled native controls, totals and an identified table in both languages", () => {
    const layers = [layer("roads", 51), layer("sites", 2)];
    const english = renderToStaticMarkup(<EvidenceFeatureBrowser layers={layers} th={false} />);
    expect(english).toContain("Table layer"); expect(english).toContain("Records 1–50 of 51");
    expect(english).toContain("<caption>"); expect(english).toContain("Source ID"); expect(english).toContain("Place 50");
    expect(english).not.toContain("Place 51"); expect(english).toContain('value="sites"');
    expect(english).toContain("Previous page"); expect(english).toContain("Next page");
    const thai = renderToStaticMarkup(<EvidenceFeatureBrowser layers={layers} th />);
    expect(thai).toContain("ชั้นข้อมูลในตาราง"); expect(thai).toContain("หน้าถัดไป"); expect(thai).toContain("รายการ 1–50 จาก 51");
  });

  it("describes image coverage without inventing per-point elevation values", () => {
    const terrain: EvidenceLibraryLayer = { id: "terrain", title: "Terrain preview", role: "Terrain context", dataset_id: "dem", availability: "available", reason: null, image_url: "/evidence-library/terrain.png", bounds: [[13, 100], [14, 101]], attribution: "Copernicus DEM" };
    const html = renderToStaticMarkup(<EvidenceFeatureBrowser layers={[terrain]} th={false} />);
    expect(html).toContain("[100, 13] → [101, 14]"); expect(html).toContain("not a point elevation measurement");
    expect(html).toContain("Copernicus DEM"); expect(html).not.toContain("Records 0");
  });
});
