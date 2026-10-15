/** "Day hike" for 0 nights, otherwise "1 night" / "3 nights". */
export function tripLengthLabel(nights: number): string {
  if (nights === 0) return "Day hike";
  return `${nights} ${nights === 1 ? "night" : "nights"}`;
}
