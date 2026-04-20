# SMOC EMS — Implementation Clarification Questions

**Document Purpose:** Pre-implementation decisions log  
**Date:** 2026-04-01  
**Status:** COMPLETE — All decisions recorded, implementation approved  

---

## Final Decisions

| # | Question | Decision |
|---|----------|----------|
| **A1** | Frontend framework | **React + Vite** |
| **A2** | Styling approach | **Tailwind CSS + Polaris brand design tokens** |
| **A3** | Charting library | **Apache ECharts** |
| **A4** | GIS library | **Leaflet.js + OpenStreetMap (offline tiles)** |
| **B1** | Backend | **Python + PostgreSQL + Docker — full backend functionality** |
| **B2** | Real-time data | **Server-Sent Events (SSE)** |
| **B3** | Auth | **JWT (self-signed, Python backend issues tokens)** |
| **C1** | REQ-1/2 renderings | **Dedicated SMOC Showcase screen inside the app** |
| **C2** | AV control room | **Simulated A/V control panel (no physical hardware dependency)** |
| **C3** | App Builder depth | **L3 Full — no-code rule engine + algorithm editor + app generator** |
| **D1** | HES/MDMS sandbox | **Mock data in PostgreSQL for now; integration layer ready to swap in live endpoints** |
| **D2** | GIS base data | **Synthetic South Africa-based LV network (feeders, transformers, meters, DER assets)** |
| **D3** | DER simulation | **Live simulation engine with real-time calculations against network model** |
| **E1** | Deployment | **Docker Compose on demo laptop — fully offline capable** |
| **E2** | Screen resolution | **4K primary (3840×2160)** |
| **E3** | Teams integration | **Live Microsoft Teams SDK integration** |
| **F1** | Build order | **Approved as-is** |

---

## Approved Build Plan

| Phase | Modules | Days |
|-------|---------|------|
| **Phase 1** | Project scaffold, design system, mock data engine, JWT auth | 1–3 |
| **Phase 2** | LV Network Dashboard, GIS Map, Alert Console | 4–8 |
| **Phase 3** | HES Mirror Panel, MDMS Mirror Panel, Energy Monitoring | 9–13 |
| **Phase 4** | DER Management, Live Simulation Engine (REQ-21–24) | 14–17 |
| **Phase 5** | Reporting, Audit, System Management, App Builder (L3) | 18–19 |
| **Phase 6** | Integration testing, dry run, polish | 20 |

---

## Tech Stack Summary

```
Frontend:  React + Vite + Tailwind CSS + Apache ECharts + Leaflet.js
Backend:   Python (FastAPI) + PostgreSQL + SSE + JWT
Infra:     Docker Compose (frontend + backend + postgres + nginx)
Auth:      JWT (self-signed, role-based: Operator / Supervisor / Admin)
GIS Data:  Synthetic SA LV network seeded into PostgreSQL
Real-time: Server-Sent Events from FastAPI to React
DER Sim:   Live network model simulation engine (Python)
AV Panel:  Simulated UI (no physical hardware dependency)
Teams:     Microsoft Teams JS SDK embedded in control room module
Display:   4K (3840×2160) primary target
```
