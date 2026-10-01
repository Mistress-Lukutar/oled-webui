/**
 * Layer-mask run helpers. The schema stores per-device masks as
 * inclusive [start, end] runs; painting and inversion need the boolean
 * coverage form and back.
 */

export type MaskRuns = [number, number][]

/** Expand inclusive runs into a boolean coverage array of `total` slots. */
export function runsToCoverage(runs: MaskRuns, total: number): boolean[] {
  const covered = new Array<boolean>(total).fill(false)
  for (const [start, end] of runs) {
    for (let i = start; i <= Math.min(end, total - 1); i += 1) covered[i] = true
  }
  return covered
}

/** Compress a boolean coverage array back into inclusive runs. */
export function coverageToRuns(covered: boolean[]): MaskRuns {
  const runs: MaskRuns = []
  let runStart: number | null = null
  for (let i = 0; i < covered.length; i += 1) {
    if (covered[i] && runStart === null) runStart = i
    if (!covered[i] && runStart !== null) {
      runs.push([runStart, i - 1])
      runStart = null
    }
  }
  if (runStart !== null) runs.push([runStart, covered.length - 1])
  return runs
}
