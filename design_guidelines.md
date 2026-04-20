# Design Guidelines: AI-Enabled Analytics Tool for Smart Metering Data

**Document Version:** 1.0  
**Date:** February 2026  
**Based on:** Polaris Brand Guidelines

---

## Table of Contents

1. [Brand Foundation](#brand-foundation)
2. [Design Philosophy](#design-philosophy)
3. [Color Palette](#color-palette)
4. [Typography](#typography)
5. [Visual Language](#visual-language)
6. [UI Components](#ui-components)
7. [Data Visualization](#data-visualization)
8. [Layout & Composition](#layout--composition)
9. [Imagery & Photography](#imagery--photography)
10. [Component Library](#component-library)

---

## Brand Foundation

### Brand Promise

Our AI-enabled analytics tool embodies **trust, innovation, and approachability** in smart metering data analysis. We transform complex energy data into actionable insights through intelligent, user-friendly design.

### Core Values

- **Trust**: Accuracy in data representation and transparent analytics
- **Innovation**: Cutting-edge AI-driven insights and predictive analytics
- **Approachability**: Demystify complex energy data through intuitive design

### Brand Personality

- **Reliable**: Honest, accurate data representation with consistent design
- **Innovative**: Future-forward analytics powered by AI
- **Curious**: Discovery-driven insights that challenge assumptions
- **Agile**: Fast, responsive interface for real-time energy management

---

## Design Philosophy

### Core Principles

1. **Minimal Aesthetic with Purpose**: Negative space is intentional; maintain 9:20 spacing ratio throughout compositions
2. **Data Fluidity**: Visual language reflects energy flow through gradient elements and subtle animations
3. **Glassmorphism**: Modern, transparent design patterns for layered information hierarchy
4. **First-Principles Approach**: Break down complex energy metrics into fundamental, understandable components
5. **Futuristic Feel**: Gradients and motion create a sense of progress and forward momentum

### Design Grid

- **Desktop**: 12-column grid with 24px gutters
- **Tablet**: 8-column grid with 16px gutters
- **Mobile**: 4-column grid with 12px gutters
- **Base Unit**: 8px spacing system (8px, 16px, 24px, 32px, 40px, 48px)

---

## Color Palette

### Primary Colors

| Color | Hex Code | Usage |
|-------|----------|-------|
| **Polaris Blue** | `#0A3690` | Primary UI elements, buttons, headers |
| **Energy Green** | `#02C9A8` | Success states, positive trends, CTAs |
| **White** | `#FCFCFC` | Backgrounds, content areas |

### Gradients

#### Primary Gradient (Main Brand Gradient)
```
Direction: 45 degrees
From: #11ABBE → To: #3C63FF → #37AAFE
Usage: Headers, cards, power visualizations
```

#### Secondary Gradient (Power Effects)
```
Direction: 45 degrees
From: #02C9A8 → To: #11ABBE
Usage: Power blur effects, glows, emphasis elements
Opacity: 50% (base), 20-30% (background)
```

#### Tertiary Gradient (Icon Accents)
```
Direction: -45 degrees
From: #2F80ED → To: #56CCF2
Usage: Icons, small UI elements, interactive states
```

### Secondary Colors

| Color | Hex Code | Usage |
|-------|----------|-------|
| **Light Gray** | `#F3F9F9` | Table rows, subtle backgrounds |
| **Accent Blue** | `#ABC7FF` | Hover states, secondary actions |
| **Dark Navy** | `#0A3690` | Text hierarchy, emphasis |

### Color Usage Rules

- **Do**: Use primary gradient on large surfaces (cards, headers)
- **Do**: Use secondary gradient only for effects (blur, glow) at defined opacity
- **Don't**: Arbitrarily extract color values from gradients
- **Don't**: Use secondary colors as fills on shapes or icons
- **Don't**: Introduce colors outside the defined palette

### Accessibility

- Maintain minimum contrast ratio of 4.5:1 for text
- Use color + pattern/icon for color-blind accessibility
- Test all color combinations for WCAG AA compliance

---

## Typography

### Font Family

**Primary Font: Satoshi**

Satoshi is a modernist sans-serif typeface that complements the brand's visual tonality. It's legible, geometric, and offers multiple weights for hierarchy.

### Type Scale

| Element | Font | Weight | Size | Line Height | Letter Spacing |
|---------|------|--------|------|-------------|-----------------|
| **Headline 1** | Satoshi | Black | 48px | 56px | 0% |
| **Headline 2** | Satoshi | Black | 36px | 44px | 0% |
| **Headline 3** | Satoshi | Bold | 28px | 36px | 4% |
| **Subheading** | Satoshi | Medium | 20px | 28px | 0% |
| **Body 1** | Satoshi | Black | 16px | 24px | 0% |
| **Body 2** | Satoshi | Medium | 14px | 20px | 0% |
| **Caption** | Satoshi | Medium | 12px | 16px | 0% |
| **Label** | Satoshi | Medium | 11px | 16px | 0.5px |

### Typography Rules

- **Do**: Use consistent line height (minimum +5pts above font size)
- **Do**: Maintain the typography hierarchy across all screens
- **Do**: Use black font weight for contrast and emphasis
- **Don't**: Reduce line height beyond +5pts
- **Don't**: Mix fonts outside the Satoshi family
- **Don't**: Use right-aligned text for body content
- **Don't**: Avoid all-caps for body text (use for labels/CTAs only)

### Web Fonts

```css
/* Primary */
font-family: 'Satoshi', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;

/* Weights to load: 400 (Medium), 700 (Bold), 900 (Black) */
```

---

## Visual Language

### Visual Concept

Our visual language celebrates energy flow and movement. We use gradient effects, glassmorphism, and subtle animations to represent the dynamic nature of energy data.

### Visual Effects

#### 1. Power Blur
**Purpose**: Background emphasis, depth creation  
**Usage**: Bottom corners of compositions, card backgrounds

**How to Create**:
1. Select a shape (circle, rectangle, or custom)
2. Duplicate and position 10% right and 10% above
3. Apply primary gradient to first shape, secondary to duplicate
4. Add 20-50% layer blur until edges are fuzzy
5. Reduce opacity to 50%

**Implementation**:
```css
/* Power Blur Effect */
filter: blur(30px);
opacity: 0.5;
background: linear-gradient(45deg, #11ABBE, #3C63FF);
```

#### 2. Power Glow
**Purpose**: Highlight important elements, draw attention  
**Usage**: Around cards, key metrics, interactive elements

**How to Create**:
- On white backgrounds: White foreground, secondary gradient background with 40% blur and 40% opacity
- On colored backgrounds: Use white glow with drop shadow

**Implementation**:
```css
/* Power Glow Effect */
box-shadow: 0 0 40px rgba(2, 201, 168, 0.4),
            0 0 20px rgba(17, 171, 190, 0.3);
filter: drop-shadow(0 0 10px rgba(255, 255, 255, 0.5));
```

#### 3. Power Streaks
**Purpose**: Background motion element, energy flow visualization  
**Usage**: Corner accents, behind content sections

**How to Create**:
1. Use gradient mesh tool or draw gradient shapes
2. Apply brand gradients
3. Apply 50%+ blur with 20-30% opacity

#### 4. Overlapping
**Purpose**: Layered information representation  
**Usage**: Icon compositions, data overlays

**Rules**:
- Use primary or tertiary gradients only
- Create 3 overlapping shapes:
  - Shape 1: Brand gradient
  - Shape 2: White gradient with background blur
  - Shape 3: Drop shadow with white gradient

#### 5. Translucency (Glassmorphism)
**Purpose**: Modern, layered interface design  
**Usage**: Cards, modals, data overlays on images

**How to Create**:
1. Use primary gradient at 40% opacity
2. Apply background blur (20-30% depending on scale)
3. White border with 10-20% opacity
4. 8px border-radius

**Implementation**:
```css
/* Glassmorphism Card */
background: linear-gradient(135deg, rgba(10, 54, 144, 0.1), rgba(2, 201, 168, 0.08));
backdrop-filter: blur(20px);
border: 1px solid rgba(255, 255, 255, 0.18);
border-radius: 8px;
```

---

## UI Components

### Buttons

#### Primary Button
```
State: Default
Background: Primary Gradient (#11ABBE → #3C63FF)
Text: White, Satoshi Bold, 16px
Padding: 12px 24px
Border Radius: 6px
Shadow: None

State: Hover
Background: Primary Gradient (10% darker)
Transform: scale(1.02)

State: Active/Pressed
Background: Primary Gradient (20% darker)
```

#### Secondary Button
```
State: Default
Background: #F3F9F9
Text: Polaris Blue (#0A3690), Satoshi Bold, 16px
Border: 1px solid #ABC7FF
Padding: 12px 24px
Border Radius: 6px

State: Hover
Background: #E8F5F5
Border: 1px solid #02C9A8
```

#### Ghost Button
```
Background: Transparent
Text: Polaris Blue (#0A3690), Satoshi Medium, 14px
Border: 2px solid #0A3690
Padding: 10px 16px
Hover: Background #F3F9F9
```

### Cards

#### Standard Card
- Background: White (#FCFCFC)
- Border Radius: 12px (top-left, top-right, bottom-right) / 8px (bottom-left)
- Shadow: 0 2px 8px rgba(0, 0, 0, 0.08)
- Padding: 24px
- Gap between cards: 16px

#### Emphasis Card (with Power Glow)
- Same as standard but with white glow effect
- Drop shadow: #0A3690 at 15% opacity
- Used for key metrics or CTAs

#### Glassmorphism Card
- Apply translucency effect (see Visual Language)
- Use on power blur backgrounds
- Ideal for overlay content

### Input Fields

```
State: Default
Border: 1px solid #ABC7FF
Background: White (#FCFCFC)
Border Radius: 6px
Padding: 10px 12px
Font: Satoshi Medium, 14px

State: Focus
Border: 2px solid #02C9A8
Shadow: 0 0 0 4px rgba(2, 201, 168, 0.1)

State: Error
Border: 2px solid #E94B4B
Shadow: 0 0 0 4px rgba(233, 75, 75, 0.1)
```

### Tags & Labels

```
Background: Linear gradient (Primary or Secondary)
Text: White, Satoshi Medium, 12px
Padding: 6px 12px
Border Radius: 4px
```

### Modals & Overlays

```
Backdrop: Black at 40% opacity
Card: White background with 8px border radius
Padding: 32px
Shadow: 0 20px 60px rgba(0, 0, 0, 0.15)
```

---

## Data Visualization

### Charts & Graphs

#### Line Chart
- **Line Weight**: 2-3px
- **Color**: Use primary gradient or brand colors
- **Grid Lines**: #ABC7FF at 10% opacity
- **Data Points**: Circle, 6px diameter, brand color fill
- **Hover State**: 8px diameter with subtle glow

#### Bar Chart
- **Bar Fill**: Primary gradient or secondary colors
- **Bar Width**: Proportional with consistent spacing
- **Shadow**: Subtle drop shadow for depth

#### Pie/Donut Chart
- **Segments**: Use gradient colors from palette
- **Center Label**: Satoshi Bold, size varies with diameter
- **Hover**: Segment highlight with slight scale increase

#### Meter/Gauge
```
Background Circle: #F3F9F9
Progress Arc: Primary gradient
Text: Satoshi Bold, 28px, #0A3690
Subtitle: Satoshi Medium, 14px, #56CCF2
```

### Data Tables

- **Header Row**: Primary gradient background, white text
- **Alternate Rows**: White and #F3F9F9
- **Borders**: Subtle, light gray (#E8E8E8)
- **Cell Padding**: 12px
- **Font**: Body 2 size

### Rules

- **Do**: Use brand colors consistently
- **Do**: Maintain minimum contrast for accessibility
- **Do**: Add hover states for interactivity
- **Don't**: Use random colors from outside the palette
- **Don't**: Use harsh gradients that reduce legibility
- **Don't**: Overcrowd charts with data labels

---

## Layout & Composition

### Spacing Rules

**9:20 Ratio Rule**: For every 9 units of content, maintain 20 units of negative space

```
Wide screens (1200px+):
- Left/Right margin: 48px
- Content max-width: 1200px

Tablet (768-1199px):
- Left/Right margin: 32px
- Content max-width: 100%

Mobile (<768px):
- Left/Right margin: 16px
- Content max-width: 100%
```

### Section Padding

```
Top/Bottom section padding: 48px (desktop), 32px (tablet), 24px (mobile)
Between sections: 64px (desktop), 48px (tablet), 32px (mobile)
```

### Alignment

- **Horizontal**: Use grid system with even distribution
- **Vertical**: Align to 8px baseline grid
- **Text**: Left-aligned for body content, center for headers
- **Icons + Text**: Vertically center with 8px gap

### Hierarchy Examples

#### Dashboard Layout
```
[Header] 
  Logo + Navigation + User Menu

[Hero Section with Gradient Background]
  - Key Metric (Large)
  - Supporting text

[Section 1: Energy Overview]
  - 3-column grid: Consumption, Savings, Efficiency
  - With power blur background elements

[Section 2: Detailed Analytics]
  - Charts with glassmorphism cards
  - Tables with brand styling

[Footer]
  - Links, copyright, support
```

---

## Imagery & Photography

### Acceptable Images

1. **People**: Ethnically diverse, candid, authentic appearances
2. **Landscapes**: Sustainable symbols, green energy, nature
3. **Data Visualization**: Modern, clean, minimal aesthetic
4. **Technology**: Futuristic, high-quality renders

### Unacceptable Images

- **Generic power symbols**: Electric poles, exposed wires, electrical hazard imagery
- **Inauthentic**: Stock photos of people posed unnaturally
- **Cluttered**: Complex backgrounds that compete with content
- **Low quality**: Pixelated, blurry, or outdated photography

### Image Treatment

#### Overlays on Images
```
Use primary blue gradient overlay (#0A3690, 100% opacity)
Or translucent glassmorphism effect
```

#### Image with Text
```
Gradient overlay: #0A3690 at 100% opacity (10% area)
Translucent glassmorphism on top/bottom or full image
Text: White or light color for contrast
```

### Photography Mood

- **Product Shoot Mood**: Minimal white palette with gradient splashes
- **Product Render Mood**: Realistic, futuristic, high-quality 3D renders
- **Lighting**: Bright, clean, with subtle shadows
- **Color Grading**: Cool tones with warm accents

---

## Component Library

### Navigation Bar

```
Height: 64px
Background: White (#FCFCFC)
Logo: Horizontal variant, 40px height
Nav Items: Satoshi Medium, 14px, #0A3690
Spacing: 32px between items
Hover State: Text color changes to Energy Green (#02C9A8)
```

### Sidebar

```
Width: 256px (collapsible to 64px)
Background: Linear gradient from #0A3690 to #0A2870
Text: White, Satoshi Medium, 14px
Icons: Tertiary gradient (#2F80ED to #56CCF2)
Active State: Green accent (#02C9A8)
Hover State: Background opacity increase
```

### Breadcrumb

```
Font: Satoshi Medium, 12px
Color: #56CCF2
Separator: "/"
Active: Polaris Blue (#0A3690)
```

### Badge

```
Background: Tertiary gradient or solid color
Text: White, Satoshi Bold, 11px
Padding: 4px 8px
Border Radius: 4px
```

### Tooltip

```
Background: Dark navy (#0A3690) with 95% opacity
Text: White, Satoshi Medium, 12px
Padding: 8px 12px
Border Radius: 4px
Shadow: 0 4px 12px rgba(0, 0, 0, 0.15)
Arrow: Triangle pointing to trigger element
```

### Notification/Alert

```
Success: Green (#02C9A8) background
Error: Red (#E94B4B) background
Warning: Orange (#FFA500) background
Info: Blue (#0A3690) background

Padding: 16px
Border Radius: 6px
Icon + Text alignment: 8px gap
Close button: Polaris Blue color
```

### Skeleton Loader

```
Base Color: #F3F9F9
Animated Shimmer: Subtle gradient sweep
Duration: 1.5s animation loop
Border Radius: Match component shape
```

---

## Motion & Animations

### Principles

- **Duration**: 300ms for quick interactions, 500ms for complex transitions
- **Easing**: Ease-out for exits, ease-in-out for state changes
- **Purpose**: Provide feedback, guide attention, maintain flow

### Common Animations

```css
/* Button interaction */
transition: all 300ms ease-out;

/* Card entrance */
animation: slideUp 500ms ease-in-out;

/* Loading state */
animation: shimmer 1.5s infinite;

/* Hover effect */
transform: translateY(-2px);
box-shadow: 0 8px 24px rgba(10, 54, 144, 0.15);
```

### Accessibility

- Respect `prefers-reduced-motion` setting
- Keep animations under 1 second for critical interactions
- Never use auto-playing animations longer than 5 seconds

---

## Responsive Design

### Breakpoints

```
Mobile: < 640px
Tablet: 640px - 1024px
Desktop: > 1024px
```

### Adaptation Rules

| Element | Mobile | Tablet | Desktop |
|---------|--------|--------|---------|
| Font Size | -2px | -1px | Base |
| Padding | 16px | 24px | 32px |
| Grid Columns | 1-2 | 2-4 | 3-4+ |
| Card Width | 100% | ~48% | ~32% |
| Navigation | Bottom Tab | Sidebar | Top + Sidebar |

### Touch-Friendly Design

- Minimum touch target: 48x48px
- Spacing between targets: 8px minimum
- Avoid hover-only interactions on mobile
- Use swipe gestures for navigation

---

## Accessibility Guidelines

### Color Contrast

- **Normal text**: Minimum 4.5:1 ratio (WCAG AA)
- **Large text**: Minimum 3:1 ratio
- **UI Components**: Minimum 3:1 ratio

### Keyboard Navigation

- All interactive elements must be accessible via Tab key
- Focus indicator visible with brand color (#02C9A8)
- Tab order logical and intuitive

### Screen Readers

- Semantic HTML (button, link, heading elements)
- Alt text for all images
- Form labels associated with inputs
- ARIA labels for complex components

### Motion & Animations

- Respect `prefers-reduced-motion` CSS media query
- Animations should not auto-play or distract
- Provide pause/play controls for animated content

---

## Code Examples

### React Component: Primary Button

```jsx
import styled from 'styled-components';

const PrimaryButton = styled.button`
  background: linear-gradient(45deg, #11ABBE, #3C63FF);
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 6px;
  font-family: 'Satoshi', sans-serif;
  font-weight: 700;
  font-size: 16px;
  cursor: pointer;
  transition: all 300ms ease-out;

  &:hover {
    transform: scale(1.02);
    box-shadow: 0 8px 24px rgba(10, 54, 144, 0.2);
  }

  &:active {
    transform: scale(0.98);
  }

  &:focus-visible {
    outline: 2px solid #02C9A8;
    outline-offset: 4px;
  }
`;
```

### CSS: Glassmorphism Card

```css
.glassmorphism-card {
  background: linear-gradient(
    135deg,
    rgba(10, 54, 144, 0.1),
    rgba(2, 201, 168, 0.08)
  );
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 8px 32px rgba(31, 38, 135, 0.15);
}
```

### SVG Gradient Definition

```xml
<defs>
  <linearGradient id="primaryGradient" x1="0%" y1="0%" x2="100%" y2="100%">
    <stop offset="0%" style="stop-color:#11ABBE;stop-opacity:1" />
    <stop offset="50%" style="stop-color:#3C63FF;stop-opacity:1" />
    <stop offset="100%" style="stop-color:#37AAFE;stop-opacity:1" />
  </linearGradient>
</defs>
```

---

## File Organization

```
/design-system
  /brand
    - logo.svg
    - color-palette.json
  /components
    - buttons.jsx
    - cards.jsx
    - charts.jsx
    - forms.jsx
    - navigation.jsx
  /styles
    - typography.css
    - colors.css
    - spacing.css
    - animations.css
  /assets
    - gradients/
    - effects/
  design-tokens.json
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Feb 2026 | Initial design guidelines for AI Analytics Tool |

---

## Contact & Support

For design system questions or contributions:
- Design System Owner: [Name/Team]
- Figma Community: [Link]
- GitHub Repository: [Link]

---

## Appendix

### Design Checklist for New Screens

- [ ] Grid system alignment verified
- [ ] Color palette used correctly
- [ ] Typography hierarchy maintained
- [ ] Spacing follows 8px baseline grid
- [ ] 9:20 negative space ratio observed
- [ ] Accessibility contrast checked
- [ ] Mobile responsive tested
- [ ] Focus states defined
- [ ] Loading and error states included
- [ ] Glassmorphism effects appropriate
- [ ] No unauthorized colors used
- [ ] Animations respect motion preferences

---

**Last Updated**: February 4, 2026  
**Maintained By**: Design Team  
**Status**: Active
