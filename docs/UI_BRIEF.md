# RepoBrain UI Art Direction & Design Brief

1. Concept: "Flight Recorder / Mission Control for Code Changes" — precise, calm, high-density telemetry for automated governance.
2. Tone: Industrial avionics instrument. Clear operational status over decorative flair; every pixel communicates state and confidence.
3. Color Ramp: Neutral slate ramp with cool blue undertone (Dark: #0a0e14 -> #121820 -> #1e2632; Light: #f8fafc -> #ffffff -> #f1f5f9).
4. Brand Accent: Precision Cyan/Cobalt (#0284c7 light / #38bdf8 dark) denoting active navigation, focus rings, and machine telemetry.
5. Semantic Signals: Pass/Allowed (Emerald #059669 / #34d399), Warn/Gate (Amber #d97706 / #fbbf24), Block/Shield (Crimson #dc2626 / #f87171), AI-Authored (Electric Iris #7c3aed / #a78bfa).
6. Accessibility: State is never conveyed by color alone (paired with geometric status icons, labels, and badges); WCAG AA contrast maintained across both light and dark modes.
7. Typography: Strict system font stack (San Francisco / Segoe UI / Roboto) with monospace + tabular-nums (ui-monospace / Menlo / Consolas) for diffs, metrics, shas, and line numbers.
8. Structure: Asymmetric layout featuring a persistent left telemetric rail (pipeline stepper, gate checklist, stage counts) and a focused primary canvas.
9. Motion & Feel: Micro-transitions <= 150ms strictly state-driven, respecting prefers-reduced-motion. Instant tactile response.
10. Anti-goals: No neon purple/cyan gamer gradients, no glassmorphism/backdrop-blur gimmicks, no emoji icons (clean geometric SVG icons only), no generic card grids.

---

## Automated WCAG 2.1 AA Contrast Verification Table

`scripts/contrast_check.py` parses the live tokens from `static/index.html` and checks every
semantic text/syntax token, UI border/focus ring, filled-control label, and tinted badge
against every surface background in both themes. Text must be >= 4.5:1 and UI components >= 3.0:1.
Current result: **ALL CHECKS PASS**.

### Dark Theme (Mission Control)

**Text & syntax tokens vs every surface**

| Token | Hex | App | Rail | Surface | Raised | Hover | Input | Target | Status |
|---|---|---|---|---|---|---|------|---|
| `--text-primary` | `#f8fafc` | 18.73:1 | 17.80:1 | 16.84:1 | 15.27:1 | 13.43:1 | 18.34:1 | 4.5:1 | PASS |
| `--text-secondary` | `#cbd5e1` | 13.20:1 | 12.54:1 | 11.86:1 | 10.76:1 | 9.46:1 | 12.93:1 | 4.5:1 | PASS |
| `--text-muted` | `#94a3b8` | 7.64:1 | 7.26:1 | 6.87:1 | 6.23:1 | 5.48:1 | 7.49:1 | 4.5:1 | PASS |
| `--brand-accent` | `#38bdf8` | 9.15:1 | 8.69:1 | 8.22:1 | 7.46:1 | 6.56:1 | 8.96:1 | 4.5:1 | PASS |
| `--signal-pass` | `#34d399` | 10.19:1 | 9.69:1 | 9.16:1 | 8.31:1 | 7.31:1 | 9.98:1 | 4.5:1 | PASS |
| `--signal-warn` | `#fbbf24` | 11.74:1 | 11.16:1 | 10.55:1 | 9.57:1 | 8.42:1 | 11.50:1 | 4.5:1 | PASS |
| `--signal-block` | `#f87171` | 7.08:1 | 6.73:1 | 6.37:1 | 5.78:1 | 5.08:1 | 6.94:1 | 4.5:1 | PASS |
| `--signal-ai` | `#a78bfa` | 7.20:1 | 6.84:1 | 6.47:1 | 5.87:1 | 5.16:1 | 7.05:1 | 4.5:1 | PASS |
| `--syn-keyword` | `#f472b6` | 7.40:1 | 7.03:1 | 6.65:1 | 6.03:1 | 5.31:1 | 7.25:1 | 4.5:1 | PASS |
| `--syn-string` | `#34d399` | 10.19:1 | 9.69:1 | 9.16:1 | 8.31:1 | 7.31:1 | 9.98:1 | 4.5:1 | PASS |
| `--syn-comment` | `#94a3b8` | 7.64:1 | 7.26:1 | 6.87:1 | 6.23:1 | 5.48:1 | 7.49:1 | 4.5:1 | PASS |
| `--syn-number` | `#38bdf8` | 9.15:1 | 8.69:1 | 8.22:1 | 7.46:1 | 6.56:1 | 8.96:1 | 4.5:1 | PASS |

**UI component borders / focus ring vs every surface**

| Token | Hex | App | Rail | Surface | Raised | Hover | Input | Target | Status |
|---|---|---|---|---|---|---|------|---|
| `--border-default` | `#6b7c93` | 4.60:1 | 4.37:1 | 4.13:1 | 3.75:1 | 3.30:1 | 4.51:1 | 3.0:1 | PASS |
| `--border-strong` | `#94a3b8` | 7.64:1 | 7.26:1 | 6.87:1 | 6.23:1 | 5.48:1 | 7.49:1 | 3.0:1 | PASS |
| `--brand-accent` | `#38bdf8` | 9.15:1 | 8.69:1 | 8.22:1 | 7.46:1 | 6.56:1 | 8.96:1 | 3.0:1 | PASS |
| `--signal-pass-border` | `#10b981` | 7.73:1 | 7.34:1 | 6.94:1 | 6.30:1 | 5.54:1 | 7.57:1 | 3.0:1 | PASS |
| `--signal-warn-border` | `#f59e0b` | 9.12:1 | 8.67:1 | 8.20:1 | 7.44:1 | 6.54:1 | 8.94:1 | 3.0:1 | PASS |
| `--signal-block-border` | `#ef4444` | 5.21:1 | 4.95:1 | 4.68:1 | 4.25:1 | 3.73:1 | 5.10:1 | 3.0:1 | PASS |
| `--signal-ai-border` | `#8b5cf6` | 4.63:1 | 4.40:1 | 4.16:1 | 3.77:1 | 3.32:1 | 4.53:1 | 3.0:1 | PASS |

**Text on filled controls**

| Text | Fill | Ratio | Target | Status |
|---|---|---|---|---|
| `--text-inverse` | `--brand-accent` (`#38bdf8`) | 9.15:1 | 4.5:1 | PASS |
| `--text-inverse` | `--brand-accent-hover` (`#0284c7`) | 4.78:1 | 4.5:1 | PASS |
| `--text-inverse` | `--signal-pass` (`#34d399`) | 10.19:1 | 4.5:1 | PASS |
| `--text-inverse` | `--signal-warn` (`#fbbf24`) | 11.74:1 | 4.5:1 | PASS |
| `--text-inverse` | `--signal-block` (`#f87171`) | 7.08:1 | 4.5:1 | PASS |
| `--text-inverse` | `--signal-ai` (`#a78bfa`) | 7.20:1 | 4.5:1 | PASS |

**Tinted badge text on composited signal backgrounds**

| Text | Badge bg | App | Rail | Surface | Raised | Hover | Input | Target | Status |
|---|---|---|---|---|---|---|---|---|---|
| `--signal-pass` | `--signal-pass-bg` | 8.10:1 | 7.50:1 | 6.99:1 | 6.24:1 | 5.52:1 | 7.88:1 | 4.5:1 | PASS |
| `--signal-warn` | `--signal-warn-bg` | 9.16:1 | 8.48:1 | 7.92:1 | 7.06:1 | 6.18:1 | 8.81:1 | 4.5:1 | PASS |
| `--signal-block` | `--signal-block-bg` | 6.54:1 | 6.10:1 | 5.76:1 | 5.20:1 | 4.54:1 | 6.35:1 | 4.5:1 | PASS |
| `--signal-ai` | `--signal-ai-bg` | 6.58:1 | 6.14:1 | 5.77:1 | 5.21:1 | 4.52:1 | 6.40:1 | 4.5:1 | PASS |

### Light Theme (Instrument Paper)

**Text & syntax tokens vs every surface**

| Token | Hex | App | Rail | Surface | Raised | Hover | Input | Target | Status |
|---|---|---|---|---|---|---|------|---|
| `--text-primary` | `#0f172a` | 16.49:1 | 15.41:1 | 17.85:1 | 17.06:1 | 15.85:1 | 17.85:1 | 4.5:1 | PASS |
| `--text-secondary` | `#1e293b` | 13.51:1 | 12.63:1 | 14.63:1 | 13.98:1 | 12.99:1 | 14.63:1 | 4.5:1 | PASS |
| `--text-muted` | `#475569` | 7.00:1 | 6.54:1 | 7.58:1 | 7.24:1 | 6.73:1 | 7.58:1 | 4.5:1 | PASS |
| `--brand-accent` | `#0369a1` | 5.48:1 | 5.12:1 | 5.93:1 | 5.67:1 | 5.27:1 | 5.93:1 | 4.5:1 | PASS |
| `--signal-pass` | `#03674a` | 6.37:1 | 5.96:1 | 6.90:1 | 6.60:1 | 6.13:1 | 6.90:1 | 4.5:1 | PASS |
| `--signal-warn` | `#92400e` | 6.55:1 | 6.12:1 | 7.09:1 | 6.78:1 | 6.29:1 | 7.09:1 | 4.5:1 | PASS |
| `--signal-block` | `#b91c1c` | 5.98:1 | 5.59:1 | 6.47:1 | 6.18:1 | 5.74:1 | 6.47:1 | 4.5:1 | PASS |
| `--signal-ai` | `#5b21b6` | 8.30:1 | 7.75:1 | 8.98:1 | 8.59:1 | 7.98:1 | 8.98:1 | 4.5:1 | PASS |
| `--syn-keyword` | `#be185d` | 5.58:1 | 5.21:1 | 6.04:1 | 5.77:1 | 5.36:1 | 6.04:1 | 4.5:1 | PASS |
| `--syn-string` | `#047857` | 5.07:1 | 4.73:1 | 5.48:1 | 5.24:1 | 4.87:1 | 5.48:1 | 4.5:1 | PASS |
| `--syn-comment` | `#52606f` | 5.95:1 | 5.56:1 | 6.44:1 | 6.15:1 | 5.72:1 | 6.44:1 | 4.5:1 | PASS |
| `--syn-number` | `#0369a1` | 5.48:1 | 5.12:1 | 5.93:1 | 5.67:1 | 5.27:1 | 5.93:1 | 4.5:1 | PASS |

**UI component borders / focus ring vs every surface**

| Token | Hex | App | Rail | Surface | Raised | Hover | Input | Target | Status |
|---|---|---|---|---|---|---|------|---|
| `--border-default` | `#768390` | 3.58:1 | 3.35:1 | 3.87:1 | 3.70:1 | 3.44:1 | 3.87:1 | 3.0:1 | PASS |
| `--border-strong` | `#475569` | 7.00:1 | 6.54:1 | 7.58:1 | 7.24:1 | 6.73:1 | 7.58:1 | 3.0:1 | PASS |
| `--brand-accent` | `#0369a1` | 5.48:1 | 5.12:1 | 5.93:1 | 5.67:1 | 5.27:1 | 5.93:1 | 3.0:1 | PASS |
| `--signal-pass-border` | `#065f46` | 7.10:1 | 6.63:1 | 7.68:1 | 7.34:1 | 6.82:1 | 7.68:1 | 3.0:1 | PASS |
| `--signal-warn-border` | `#78350f` | 8.38:1 | 7.83:1 | 9.07:1 | 8.67:1 | 8.05:1 | 9.07:1 | 3.0:1 | PASS |
| `--signal-block-border` | `#991b1b` | 7.68:1 | 7.17:1 | 8.31:1 | 7.94:1 | 7.38:1 | 8.31:1 | 3.0:1 | PASS |
| `--signal-ai-border` | `#4c1d95` | 10.12:1 | 9.46:1 | 10.95:1 | 10.47:1 | 9.73:1 | 10.95:1 | 3.0:1 | PASS |

**Text on filled controls**

| Text | Fill | Ratio | Target | Status |
|---|---|---|---|---|
| `--text-inverse` | `--brand-accent` (`#0369a1`) | 5.93:1 | 4.5:1 | PASS |
| `--text-inverse` | `--brand-accent-hover` (`#075985`) | 7.56:1 | 4.5:1 | PASS |
| `--text-inverse` | `--signal-pass` (`#03674a`) | 6.90:1 | 4.5:1 | PASS |
| `--text-inverse` | `--signal-warn` (`#92400e`) | 7.09:1 | 4.5:1 | PASS |
| `--text-inverse` | `--signal-block` (`#b91c1c`) | 6.47:1 | 4.5:1 | PASS |
| `--text-inverse` | `--signal-ai` (`#5b21b6`) | 8.98:1 | 4.5:1 | PASS |

**Tinted badge text on composited signal backgrounds**

| Text | Badge bg | App | Rail | Surface | Raised | Hover | Input | Target | Status |
|---|---|---|---|---|---|---|---|---|---|
| `--signal-pass` | `--signal-pass-bg` | 5.33:1 | 5.00:1 | 5.75:1 | 5.49:1 | 5.12:1 | 5.75:1 | 4.5:1 | PASS |
| `--signal-warn` | `--signal-warn-bg` | 5.45:1 | 5.12:1 | 5.88:1 | 5.65:1 | 5.27:1 | 5.88:1 | 4.5:1 | PASS |
| `--signal-block` | `--signal-block-bg` | 4.90:1 | 4.59:1 | 5.29:1 | 5.04:1 | 4.70:1 | 5.29:1 | 4.5:1 | PASS |
| `--signal-ai` | `--signal-ai-bg` | 6.73:1 | 6.31:1 | 7.25:1 | 6.97:1 | 6.49:1 | 7.25:1 | 4.5:1 | PASS |
