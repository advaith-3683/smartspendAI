export const STATUS_COLORS = {
  on_track: { solid: '#34E5C7', bright: '#7FFFE0', glow: 'rgba(52, 229, 199, 0.45)' },
  at_risk: { solid: '#FFC857', bright: '#FFE29A', glow: 'rgba(255, 200, 87, 0.45)' },
  over_budget: { solid: '#FF5C7A', bright: '#FF9BAF', glow: 'rgba(255, 92, 122, 0.5)' },
}

export function getStatusColors(status) {
  return STATUS_COLORS[status] || STATUS_COLORS.on_track
}
