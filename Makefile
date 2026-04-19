# Convenience make targets. Windows users can also use ./scripts/perfection.ps1.

.PHONY: perfection perfection-dry perfection-reset perfection-phase

perfection:
	cd backend && python -m scripts.perfection_loop

perfection-dry:
	cd backend && python -m scripts.perfection_loop --dry-run

perfection-reset:
	cd backend && python -m scripts.perfection_loop --reset-state

# Usage: make perfection-phase PHASES="unit_backend,unit_frontend"
perfection-phase:
	cd backend && python -m scripts.perfection_loop --phases "$(PHASES)"
