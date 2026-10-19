export const STATUS_COLORS = {
  on_track: { solid: '#91dfbb', bright: '#b4ebd1', glow: 'transparent' },
  at_risk: { solid: '#f0ce8d', bright: '#f6dfb2', glow: 'transparent' },
  over_budget: { solid: '#ffb6ad', bright: '#ffd1cb', glow: 'transparent' },
}
export function getStatusColors(status) {
  return STATUS_COLORS[status] || STATUS_COLORS.on_track
}
