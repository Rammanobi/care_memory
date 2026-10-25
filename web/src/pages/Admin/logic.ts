// Pure helpers for the Admin page (unit tested).
import type { UsageMode } from "../../api";

/** What happens next at the cap, by mode. Thresholds are the AMBER (70%) and RED (90%) lines. */
export function nextChange(mode: UsageMode, cap: number): string {
  const usd = (f: number) => `$${(cap * f).toFixed(2)}`;
  if (mode === "GREEN") return `Next change at 70% of today's cap (${usd(0.7)}): AMBER, the saving mode.`;
  if (mode === "AMBER") return `Next change at 90% of today's cap (${usd(0.9)}): RED, template-only.`;
  return "Template-only until the cap resets. Approved messages and rules still work.";
}

/** Top of the spend chart: the cap or the highest day, rounded up, so every bar and cap line is inside. */
export function spendDomainMax(spends: number[], cap: number): number {
  const top = Math.max(cap, ...spends.filter((n) => Number.isFinite(n)));
  return Math.max(1, Math.ceil(top));
}
