/**
 * Pure, dependency-free gear-matching logic shared by gearRecommendation.ts.
 * Kept separate (no Supabase import) so it can be unit tested directly with
 * plain Node, without needing a bundler to resolve path aliases.
 */

export interface RatedVariant {
  variant_name: string;
  min_temp_c: number;
  min_r_value: number | null;
  /** Per-unit weight in grams for THIS variant, when set. Falls back to the
   * parent gear_items.weight_g at the call site if null. */
  weight_g: number | null;
}

/**
 * The ONE place gram values from the database get converted to pounds.
 * Every weight exposed by gearRecommendation.ts is already in pounds —
 * callers should never see or convert weight_g directly.
 */
export function gramsToLb(grams: number): number {
  return grams / 453.592;
}

/**
 * Pick the lightest/warmest-adequate variant (highest min_temp_c at or below
 * the target), falling back to the warmest-rated variant overall (lowest
 * min_temp_c = most protective) if nothing is adequate.
 */
export function pickAdequateVariant(
  variants: RatedVariant[],
  targetTempC: number,
): { variant: RatedVariant; isFallback: boolean } {
  if (variants.length === 0) {
    throw new Error("No temperature-rated variants to choose from");
  }

  const sorted = [...variants].sort((a, b) => a.min_temp_c - b.min_temp_c);
  const adequate = sorted.filter((v) => v.min_temp_c <= targetTempC);

  if (adequate.length > 0) {
    const warmestAdequate = adequate.reduce((best, v) =>
      v.min_temp_c > best.min_temp_c ? v : best,
    );
    return { variant: warmestAdequate, isFallback: false };
  }

  return { variant: sorted[0], isFallback: true };
}
