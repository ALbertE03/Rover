"""Visualización del terreno: el generador crea el mapa y este módulo
dibuja el HTML con el pipeline completo. Sin simulación: solo terrenos."""

from .terreno import build_html, pipeline_data, render_html

__all__ = ["build_html", "pipeline_data", "render_html"]
