"""
Servicio de estadísticas y analytics
"""
from datetime import datetime, timedelta
from typing import Dict, List
from sqlalchemy import func, extract
from app import db
from app.models import Tool, Entry, Update, AgentRun


class StatsService:
    """Analytics del sistema"""
    
    @staticmethod
    def get_dashboard_stats() -> Dict:
        """Estadísticas generales para el dashboard"""
        
        # Total de herramientas activas
        total_tools = Tool.query.filter_by(status='active').count()
        
        # Total de entradas
        total_entries = Entry.query.count()
        
        # Última entrada
        last_entry = Entry.query.order_by(Entry.date.desc()).first()
        
        # Total de actualizaciones
        total_updates = Update.query.count()
        
        # Última ejecución del agente
        last_agent_run = AgentRun.query.order_by(AgentRun.started_at.desc()).first()
        
        # Total de ejecuciones del agente
        total_agent_runs = AgentRun.query.count()
        
        # Calidad promedio
        avg_quality_result = db.session.query(
            func.avg(AgentRun.completeness)
        ).filter(AgentRun.completeness.isnot(None)).scalar()
        avg_quality = float(avg_quality_result) if avg_quality_result else None
        
        # Costo total
        total_cost_result = db.session.query(
            func.sum(AgentRun.total_cost_usd)
        ).filter(AgentRun.total_cost_usd.isnot(None)).scalar()
        total_cost = float(total_cost_result) if total_cost_result else 0.0
        
        # Herramientas por campo disciplinar
        tools_by_field = db.session.query(
            Tool.field,
            func.count(Tool.id).label('count')
        ).filter(Tool.status == 'active', Tool.field.isnot(None)).group_by(Tool.field).order_by(func.count(Tool.id).desc()).all()
        
        # Herramientas por categoría
        tools_by_category = db.session.query(
            Tool.category,
            func.count(Tool.id).label('count')
        ).filter(Tool.status == 'active', Tool.category.isnot(None)).group_by(Tool.category).order_by(func.count(Tool.id).desc()).all()
        
        return {
            'total_tools': total_tools,
            'total_entries': total_entries,
            'total_updates': total_updates,
            'total_agent_runs': total_agent_runs,
            'avg_quality': avg_quality,
            'total_cost': total_cost,
            'last_entry': {
                'date': last_entry.date.isoformat() if last_entry else None,
                'tools_count': len(last_entry.tools) if last_entry else 0,
                'updates_count': len(last_entry.updates) if last_entry else 0,
            } if last_entry else None,
            'last_agent_run': {
                'started_at': last_agent_run.started_at.isoformat() if last_agent_run else None,
                'status': last_agent_run.status if last_agent_run else None,
                'duration': last_agent_run.duration_seconds if last_agent_run else None,
            } if last_agent_run else None,
            'by_field': [(field, count) for field, count in tools_by_field if field],
            'by_category': [(cat, count) for cat, count in tools_by_category if cat],
            'tools_by_field': {field: count for field, count in tools_by_field if field},
            'tools_by_category': {cat: count for cat, count in tools_by_category if cat},
        }
    
    @staticmethod
    def get_agent_quality_trends(days: int = 30) -> List[Dict]:
        """
        Tendencias de calidad del agente
        
        Args:
            days: Últimos N días
            
        Returns:
            Lista de {date, completeness, diversity, hallucination_risk}
        """
        since = datetime.utcnow() - timedelta(days=days)
        
        runs = AgentRun.query.filter(
            AgentRun.started_at >= since,
            AgentRun.status == 'success'
        ).order_by(AgentRun.started_at).all()
        
        return [{
            'date': run.started_at.date().isoformat(),
            'completeness': run.completeness,
            'diversity': run.field_diversity,
            'social_coverage': run.social_coverage,
            'hallucination_risk': run.hallucination_risk,
        } for run in runs if run.completeness is not None]
    
    @staticmethod
    def get_tools_timeline(months: int = 12) -> List[Dict]:
        """
        Timeline de nuevas herramientas por mes
        
        Args:
            months: Últimos N meses
            
        Returns:
            Lista de {year, month, count}
        """
        since = datetime.utcnow() - timedelta(days=months*30)
        
        timeline = db.session.query(
            extract('year', Tool.first_seen).label('year'),
            extract('month', Tool.first_seen).label('month'),
            func.count(Tool.id).label('count')
        ).filter(
            Tool.first_seen >= since
        ).group_by('year', 'month').order_by('year', 'month').all()
        
        return [{
            'year': int(year),
            'month': int(month),
            'count': count
        } for year, month, count in timeline]
    
    @staticmethod
    def get_agent_cost_summary(days: int = 30) -> Dict:
        """
        Resumen de costos del agente
        
        Args:
            days: Últimos N días
            
        Returns:
            Dict con total_cost, total_tokens, avg_cost_per_run
        """
        since = datetime.utcnow() - timedelta(days=days)
        
        result = db.session.query(
            func.sum(AgentRun.total_cost_usd).label('total_cost'),
            func.sum(AgentRun.total_tokens).label('total_tokens'),
            func.avg(AgentRun.total_cost_usd).label('avg_cost'),
            func.count(AgentRun.id).label('runs')
        ).filter(
            AgentRun.started_at >= since,
            AgentRun.status == 'success'
        ).first()
        
        return {
            'total_cost_usd': float(result.total_cost or 0),
            'total_tokens': int(result.total_tokens or 0),
            'avg_cost_per_run': float(result.avg_cost or 0),
            'total_runs': int(result.runs or 0),
        }
