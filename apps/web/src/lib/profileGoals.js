export const JOUFT_GOAL_OPTIONS = [
  'Refresh My Closet',
  'Sustainable Fashion',
  'Trade Instead of Sell',
  'Access Luxury Fashion',
]

export function normalizeProfileGoals(goals) {
  if (!Array.isArray(goals) || goals.some((goal) => !JOUFT_GOAL_OPTIONS.includes(goal))) return []
  return [...new Set(goals)].slice(0, 2)
}

export function needsGoalSelection(goals) {
  return !Array.isArray(goals) || goals.length === 0 || goals.length > 2
    || goals.some((goal) => !JOUFT_GOAL_OPTIONS.includes(goal))
}
