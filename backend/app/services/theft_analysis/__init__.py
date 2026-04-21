"""Theft-analysis service — NTL (non-technical loss) scoring for Polaris EMS.

Reads metrology + event data from the MDMS ``validation_rules`` postgres,
runs a suite of rule + statistical detectors per meter, and persists a
ranked theft score + evidence payload back to Polaris for the UI.

Subpackages:
    mdms_client   — read-only fetchers against validation_rules
    detectors     — individual signal detectors (flat-line, reverse-energy …)
    scorer        — combines detector outputs into a per-meter score
"""
