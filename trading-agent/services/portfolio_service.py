# ==============================================================================
# File: services/portfolio_service.py
# ==============================================================================

"""
Portfolio & Position Application Service Compatibility Shim.
Re-exports canonical implementation from monika.application.services.portfolio_service.
"""

from monika.application.services.portfolio_service import PortfolioService

__all__ = ["PortfolioService"]
