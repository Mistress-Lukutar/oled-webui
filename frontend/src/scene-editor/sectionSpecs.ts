/**
 * Registry of device sections in a scene file. Every device kind the
 * application understands registers one entry: its YAML key, label,
 * client-side validator and a default section factory for "+ Add
 * section". Adding a device = a validator + one entry here (plus a view
 * mapping in sectionViews.ts and a backend section/runtime).
 */

import { validateArgbSection } from '../argb/schemaCheck'
import { defaultLayout } from '../argb/types'
import { validateScreenSection } from './yamlSync'
import type { SectionSpecData } from './yamlSync'

export interface SectionSpec extends SectionSpecData {
  key: string
  label: string
  /** Build the initial section content for "+ Add section". */
  createDefault(): Record<string, unknown>
}

export const SECTION_SPECS: SectionSpec[] = [
  {
    key: 'screen',
    label: 'Screen',
    validate: validateScreenSection,
    createDefault: () => ({}),
  },
  {
    key: 'argb',
    label: 'ARGB',
    validate: validateArgbSection,
    createDefault: () => defaultLayout() as unknown as Record<string, unknown>,
  },
]

export function sectionSpec(key: string): SectionSpec | undefined {
  return SECTION_SPECS.find((spec) => spec.key === key)
}
