/**
 * The demo hiker the landing page offers ("See a demo profile"). Kept in step
 * with backend app/demo_data.py FEATURED_DEMO; the link only shows while
 * that profile exists, so removing the demo accounts removes it too.
 */
export const FEATURED_DEMO = "demo_maya";

export const demoProfileHref = `/u/${FEATURED_DEMO}`;
