export function metersToFeet(meters: number): number {
  return Math.round(meters * 3.28084);
}

export function celsiusToFahrenheit(celsius: number): number {
  return Math.round((celsius * 9) / 5 + 32);
}
