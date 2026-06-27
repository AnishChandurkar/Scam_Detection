# Agent Developer Guide

Welcome! This repository implements a platform-agnostic **Finfluencer Scam Detection Engine** to scan and identify potential financial scams in social media posts.

---

## Project Specification & Reference

For the full specification, check logic details, scoring weights, API definition, and stack information, refer to:

* **[CLAUDE.md](CLAUDE.md)** — Contains the system architecture, input/output JSON schemas, and check details.

---

## Architecture & Implementation Notes

When working as an agent on this codebase, keep the following in mind:

1. **Modular Checks**: All checks (NLP, SEBI registration, and Market Anomaly) are located in the `engine/checks/` directory and must run independently.
2. **Scoring and Configuration**: Scoring rules are combined in `engine/scoring/scorer.py` according to parameters in `engine/config.py`.
3. **Inputs/Outputs**:
   - Inputs are normalized using `engine/utils/normaliser.py` before checks run.
   - Failures in individual checks should be handled gracefully (e.g., fallback/neutral scores) instead of raising exceptions.
