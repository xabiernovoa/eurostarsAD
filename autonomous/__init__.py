"""
autonomous — Sistema autónomo de marketing por email para Eurostars.

Arquitectura basada en heartbeat: un bucle periódico que consulta un Oráculo
externo, decide a qué usuarios contactar y genera campañas personalizadas
reutilizando los módulos del pipeline existente.
"""

__version__ = "0.1.0"
