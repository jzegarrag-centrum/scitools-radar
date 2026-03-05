"""
Servicio de búsqueda full-text en PostgreSQL
"""
from typing import List, Optional
from sqlalchemy import func, or_, case
from app import db
from app.models import Tool


class SearchService:
    """Full-text search en herramientas"""
    
    @staticmethod
    def search_tools(
        query: str,
        field: Optional[str] = None,
        category: Optional[str] = None,
        pricing: Optional[str] = None,
        limit: int = 20
    ) -> List[Tool]:
        """
        Búsqueda full-text de herramientas
        
        Args:
            query: Término de búsqueda
            field: Filtrar por campo disciplinar
            category: Filtrar por categoría
            pricing: Filtrar por modelo de pricing (free, open-source, freemium, paid)
            limit: Máximo resultados
            
        Returns:
            Lista de Tool ordenados por relevancia
        """
        # Base query
        q = Tool.query.filter(Tool.status == 'active')
        
        # Full-text search en name y summary
        if query:
            search_filter = or_(
                Tool.name.ilike(f'%{query}%'),
                Tool.summary.ilike(f'%{query}%')
            )
            q = q.filter(search_filter)
        
        # Filtros adicionales
        if field:
            q = q.filter(Tool.field == field)
        
        if category:
            q = q.filter(Tool.category == category)

        if pricing:
            q = q.filter(Tool.pricing == pricing)
        
        # Orden por relevancia (nombre primero, luego summary)
        if query:
            q = q.order_by(
                case(
                    (Tool.name.ilike(f'%{query}%'), 1),
                    else_=0
                ).desc(),
                Tool.last_updated.desc()
            )
        else:
            q = q.order_by(Tool.last_updated.desc())
        
        return q.limit(limit).all()
    
    @staticmethod
    def get_all_fields() -> List[str]:
        """Retorna todos los campos disciplinares únicos"""
        result = db.session.query(Tool.field).distinct().filter(Tool.field.isnot(None)).all()
        return sorted([r[0] for r in result])
    
    @staticmethod
    def get_all_categories() -> List[str]:
        """Retorna todas las categorías únicas"""
        result = db.session.query(Tool.category).distinct().filter(Tool.category.isnot(None)).all()
        return sorted([r[0] for r in result])

    @staticmethod
    def get_all_pricings() -> List[str]:
        """Retorna todos los modelos de pricing únicos"""
        result = db.session.query(Tool.pricing).distinct().filter(Tool.pricing.isnot(None)).all()
        return sorted([r[0] for r in result])
