export type ScenarioPoint = readonly [number, number];
export interface ScenarioNode { readonly id: string; readonly position: ScenarioPoint }
export interface ScenarioLink { readonly id: string; readonly from: string; readonly to: string }

export const ILLUSTRATIVE_SCENARIO = {
  id: "SYN-ACCESS-01",
  origin: "synthetic_illustration",
  sourceStatus: "authored_not_observed",
  currentConditionClaim: false,
  operationalWriteAllowed: false,
  homeId: "SYN-HOME-A",
  facilityId: "SYN-FACILITY-A",
  assumedDisruptedLinkId: "SYN-LINK-CROSSING",
  nodes: [
    { id: "SYN-HOME-A", position: [-9, -4.05] },
    { id: "SYN-NODE-ENTRY", position: [-9, -3.65] },
    { id: "SYN-NODE-WEST", position: [-4.3, -3.65] },
    { id: "SYN-NODE-BEFORE", position: [-4.3, -1.1] },
    { id: "SYN-NODE-AFTER", position: [-4.3, 1.25] },
    { id: "SYN-NODE-JUNCTION", position: [-4.3, 2.7] },
    { id: "SYN-NODE-CENTER", position: [-2.25, 2.3] },
    { id: "SYN-NODE-FRONTAGE", position: [-2, 6] },
    { id: "SYN-NODE-GATE", position: [1.1, 5.8] },
    { id: "SYN-FACILITY-A", position: [1.1, 5.35] },
    { id: "SYN-NODE-SPUR", position: [-12, -3.65] },
  ] as const satisfies readonly ScenarioNode[],
  links: [
    { id: "SYN-LINK-DRIVE", from: "SYN-HOME-A", to: "SYN-NODE-ENTRY" },
    { id: "SYN-LINK-WEST", from: "SYN-NODE-ENTRY", to: "SYN-NODE-WEST" },
    { id: "SYN-LINK-APPROACH", from: "SYN-NODE-WEST", to: "SYN-NODE-BEFORE" },
    { id: "SYN-LINK-CROSSING", from: "SYN-NODE-BEFORE", to: "SYN-NODE-AFTER" },
    { id: "SYN-LINK-EXIT", from: "SYN-NODE-AFTER", to: "SYN-NODE-JUNCTION" },
    { id: "SYN-LINK-JUNCTION", from: "SYN-NODE-JUNCTION", to: "SYN-NODE-CENTER" },
    { id: "SYN-LINK-FRONTAGE", from: "SYN-NODE-CENTER", to: "SYN-NODE-FRONTAGE" },
    { id: "SYN-LINK-GATE", from: "SYN-NODE-FRONTAGE", to: "SYN-NODE-GATE" },
    { id: "SYN-LINK-FACILITY", from: "SYN-NODE-GATE", to: "SYN-FACILITY-A" },
    { id: "SYN-LINK-SPUR", from: "SYN-NODE-ENTRY", to: "SYN-NODE-SPUR" },
  ] as const satisfies readonly ScenarioLink[],
  floodFootprint: [
    [19,-1.9],[17,-2.1],[15.8,-1.8],[14,-1.9],[12.8,-1.55],[11,-1.5],[9.9,-1.9],
    [8,-1.75],[7,-1.4],[5.8,-1.65],[5,-1.35],[4,-1.25],[2.8,-1.65],[1.4,-1.2],
    [.2,-1.4],[-.8,-1.1],[-2.3,-1.05],[-3,-.75],[-3.7,-.85],[-4.3,-.8],[-4.65,-.95],[-5.05,-.7],[-5.25,-.6],
    [-5.4,.05],[-5.22,.3],[-5.05,.75],[-4.6,1.15],[-4,1.03],[-3.5,1.2],[-2.8,.85],[-2.1,.85],
    [-1,.45],[.2,.6],[1.3,.37],[2.5,.75],[3.7,.3],[4.6,.62],[5.5,.6],[6.6,.93],
    [8,1.1],[9.2,.7],[11,.95],[12.2,1.5],[13,1.25],[14,1.5],[15.7,1.7],[17,1.55],[19,2.2],
  ] as const satisfies readonly ScenarioPoint[],
  annotationAnchors: { home: [-9, 1.3, -5], facility: [2.6, 1.55, 3.76], affectedLink: [-4.3, .4, .075] } as const,
  assumptions: [
    "Only the explicitly drawn synthetic links are included; surrounding streets are geographic context, not a complete transport network.",
    "The crossing link is removed as an illustrative disruption assumption. Water overlap does not establish actual road status.",
    "The destination is illustrative; current facility operation, road status and alternative connections are unverified.",
    "No population, distance, travel time, facility capacity or real-world priority score is claimed.",
  ],
} as const;

/** Unweighted reachability within the supplied bounded undirected graph, not road-status inference. */
export function findScenarioPath(nodes: readonly ScenarioNode[], links: readonly ScenarioLink[], from: string, to: string, removedLinks: ReadonlySet<string> = new Set()): readonly string[] | null {
  const ids = new Set(nodes.map(node => node.id));
  if (!ids.has(from) || !ids.has(to)) return null;
  const adjacency = new Map(nodes.map(node => [node.id, [] as { node: string; link: string }[]]));
  for (const link of links) {
    if (!ids.has(link.from) || !ids.has(link.to)) throw new Error(`Unknown endpoint on ${link.id}`);
    if (removedLinks.has(link.id)) continue;
    adjacency.get(link.from)!.push({ node: link.to, link: link.id });
    adjacency.get(link.to)!.push({ node: link.from, link: link.id });
  }
  const queue = [from], previous = new Map<string, { node: string; link: string } | null>([[from, null]]);
  for (let index = 0; index < queue.length; index++) {
    const current = queue[index];
    if (current === to) {
      const path: string[] = [];
      let node = to;
      while (previous.get(node)) { const parent = previous.get(node)!; path.unshift(parent.link); node = parent.node; }
      return path;
    }
    for (const edge of adjacency.get(current)!) if (!previous.has(edge.node)) {
      previous.set(edge.node, { node: current, link: edge.link }); queue.push(edge.node);
    }
  }
  return null;
}

/** Pure result, with no link removal inferred from the illustrative water geometry. */
export function evaluateIllustrativeScenario() {
  const scenario = ILLUSTRATIVE_SCENARIO;
  const baselinePath = findScenarioPath(scenario.nodes, scenario.links, scenario.homeId, scenario.facilityId);
  const scenarioPath = findScenarioPath(scenario.nodes, scenario.links, scenario.homeId, scenario.facilityId, new Set([scenario.assumedDisruptedLinkId]));
  return { scenarioId: scenario.id, baselineReachable: baselinePath !== null, scenarioReachable: scenarioPath !== null, baselinePath, scenarioPath,
    removedLinkId: scenario.assumedDisruptedLinkId, origin: scenario.origin, currentConditionClaim: false, operationalWriteAllowed: false } as const;
}

/** Evaluate explicitly removed synthetic links; no geometry-derived closure inference. */
export function evaluateIllustrativeAccess(blockedLinkIds: readonly string[] = []) {
  const scenario = ILLUSTRATIVE_SCENARIO;
  const linkIds = findScenarioPath(scenario.nodes, scenario.links, scenario.homeId, scenario.facilityId, new Set(blockedLinkIds));
  return { reachable: linkIds !== null, linkIds, origin: scenario.origin } as const;
}

export const ILLUSTRATIVE_FINDING = {
  scenarioId: ILLUSTRATIVE_SCENARIO.id,
  baseline: evaluateIllustrativeAccess(),
  scenario: evaluateIllustrativeAccess([ILLUSTRATIVE_SCENARIO.assumedDisruptedLinkId]),
  assumedDisruptedLinkId: ILLUSTRATIVE_SCENARIO.assumedDisruptedLinkId,
  assumptions: ILLUSTRATIVE_SCENARIO.assumptions,
  origin: ILLUSTRATIVE_SCENARIO.origin,
  currentConditionClaim: false,
  operationalWriteAllowed: false,
} as const;

/** Point containment for the authored flood footprint; boundary points count as affected. */
export function insideIllustrativeFlood([x, z]: ScenarioPoint): boolean {
  const polygon = ILLUSTRATIVE_SCENARIO.floodFootprint;
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [ax, az] = polygon[i], [bx, bz] = polygon[j];
    const cross = (x - ax) * (bz - az) - (z - az) * (bx - ax);
    if (Math.abs(cross) < 1e-8 && x >= Math.min(ax, bx) && x <= Math.max(ax, bx) && z >= Math.min(az, bz) && z <= Math.max(az, bz)) return true;
    if ((az > z) !== (bz > z) && x < (bx - ax) * (z - az) / (bz - az) + ax) inside = !inside;
  }
  return inside;
}
