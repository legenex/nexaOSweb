import type { Schemas } from '@nexaosweb/api-client';

type Project = Schemas['ProjectRead'];

// The fixed research library categories, in display order.
export const RESEARCH_CATEGORIES = [
  'market',
  'technical',
  'competitor',
  'lead generation',
  'product',
  'personal',
] as const;

export type ResearchCategory = (typeof RESEARCH_CATEGORIES)[number];

const KEYWORDS: Record<ResearchCategory, string[]> = {
  market: ['market', 'audience', 'pricing', 'segment', 'demand', 'tam'],
  technical: ['technical', 'api', 'infra', 'stack', 'architecture', 'engineering', 'platform'],
  competitor: ['competitor', 'rival', 'compare', 'comparison', 'benchmark', 'alternative'],
  'lead generation': [
    'lead',
    'funnel',
    'acquisition',
    'outreach',
    'ads',
    'campaign',
    'growth',
    'advertorial',
    'quiz',
  ],
  product: ['product', 'feature', 'roadmap', 'ux', 'design', 'page', 'web'],
  personal: ['personal', 'journal', 'habit', 'health', 'life'],
};

// A simple, deterministic category from the project name and slug. Defaults to product when
// nothing matches, so every project lands in exactly one library group.
export function categorize(project: Project): ResearchCategory {
  const haystack = `${project.name} ${project.slug}`.toLowerCase();
  for (const category of RESEARCH_CATEGORIES) {
    if (KEYWORDS[category].some((word) => haystack.includes(word))) return category;
  }
  return 'product';
}

export function groupByCategory(projects: Project[]): Record<ResearchCategory, Project[]> {
  const groups = Object.fromEntries(
    RESEARCH_CATEGORIES.map((category) => [category, [] as Project[]]),
  ) as Record<ResearchCategory, Project[]>;
  for (const project of projects) groups[categorize(project)].push(project);
  return groups;
}
