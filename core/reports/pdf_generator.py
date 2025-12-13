# core/reports/pdf_generator.py
import io
import json
import os
import uuid
from datetime import datetime
from django.conf import settings
from django.template.loader import render_to_string
from django.db.models import Count, Avg
from django.utils.text import slugify
from django.db import connection

# Se asume que tienes WeasyPrint instalado y configurado
try:
    from weasyprint import HTML
except ImportError:
    class HTML:
        """Mock class if WeasyPrint is not installed."""
        def __init__(self, string, base_url):
            pass
        def write_pdf(self, target):
            target.write(b"WeasyPrint is not installed.")

# --- HELPERS ---

class DataNormalizer:
    """Clase de utilidades para preparar datos para la vista de reportes."""
    
    @staticmethod
    def _get_q_text(question_id, analysis_data):
        """Busca el texto de la pregunta por ID."""
        for item in analysis_data:
            if item.get('id') == question_id:
                return item.get('text', f"Pregunta ID {question_id}")
        return f"ID {question_id} (No encontrado)"

    @staticmethod
    def prepare_consolidated_rows(analysis_data):
        """Prepara una tabla resumida con métricas clave para la primera página."""
        rows = []
        for item in analysis_data:
            q_type = item.get('type')
            
            summary = ""
            if q_type in ['scale', 'number'] and item.get('avg') is not None:
                summary = f"Promedio: {item['avg']:.1f} / {item['max']:.0f}"
            elif q_type in ['single', 'multi'] and item.get('opciones'):
                top_opt = sorted(item['opciones'], key=lambda x: x['count'], reverse=True)
                if top_opt:
                    summary = f"Top: {top_opt[0]['label'][:30]}... ({top_opt[0]['percent']:.0f}%)"
            elif q_type == 'text':
                summary = f"{item.get('total_respuestas', 0)} respuestas de texto"
            
            if summary:
                rows.append({
                    'id': item['id'],
                    'text': item['text'],
                    'type': item.get('tipo_display', q_type),
                    'summary': summary,
                    'total': item.get('total_respuestas', 0)
                })
        return rows


# --- SERVICIO DE REPORTES PDF ---

class PDFReportGenerator:
    PDF_BASE_PATH = os.path.join(settings.MEDIA_ROOT, 'reports', 'pdf')
    PDF_PUBLIC_URL = os.path.join(settings.MEDIA_URL, 'reports', 'pdf')

    @staticmethod
    def _render_to_pdf_bytes(template_name, context, request=None):
        """Renderiza la plantilla HTML a bytes PDF usando WeasyPrint."""
        html_string = render_to_string(template_name, context, request=request)
        
        # WeasyPrint necesita un base_url para cargar CSS y estáticos
        base_url = request.build_absolute_uri('/') if request else None

        html = HTML(string=html_string, base_url=base_url)
        pdf_bytes = html.write_pdf()
        return pdf_bytes

    @staticmethod
    def _save_pdf_to_storage(pdf_bytes, filename):
        """Guarda los bytes PDF en el sistema de archivos."""
        os.makedirs(PDFReportGenerator.PDF_BASE_PATH, exist_ok=True)
        file_path = os.path.join(PDFReportGenerator.PDF_BASE_PATH, filename)
        with open(file_path, 'wb') as f:
            f.write(pdf_bytes)
        
        # Devuelve la URL pública para ser accedida por el usuario
        public_url = os.path.join(PDFReportGenerator.PDF_PUBLIC_URL, filename)
        return public_url, file_path

    @staticmethod
    def generate_report(
        survey, analysis_data, nps_data, total_responses, 
        kpi_satisfaction_avg, include_table, include_kpis, 
        include_charts, request, start_date=None, end_date=None
    ):
        """Genera el PDF para un solo Survey."""
        context = {
            'survey': survey,
            'total_respuestas': total_responses,
            'kpi_satisfaction_avg': kpi_satisfaction_avg,
            'nps_data': nps_data,
            'analysis_data': analysis_data,
            'generated_at': datetime.now(),
            'start_date': start_date,
            'end_date': end_date,
            'include_table': include_table,
            'include_kpis': include_kpis,
            'include_charts': include_charts,
            'consolidated_table_rows': DataNormalizer.prepare_consolidated_rows(analysis_data)
        }
        
        # Renderiza y devuelve los bytes (la vista se encarga de la respuesta HTTP)
        return PDFReportGenerator._render_to_pdf_bytes(
            'core/reports/report_pdf_template.html', 
            context, 
            request=request
        )

    @staticmethod
    def generate_global_report(data, request=None):
        """Genera el PDF para el Dashboard Global."""
        context = {
            'data': data,
            'generated_at': datetime.now(),
            'periodo_str': data.get('periodo', '30 días'),
        }
        
        return PDFReportGenerator._render_to_pdf_bytes(
            'core/reports/_global_results_pdf.html', 
            context, 
            request=request
        )

# --- CELERY TASK SERVICE (Nueva lógica para Asincronía) ---

class ReportAsyncService:
    """
    Gestiona la ejecución asíncrona de generación de reportes y guarda
    el estado en la base de datos (se asume un modelo ReportJob en core/models_reports.py
    o similar para guardar el estado y la URL del archivo).
    """

    @staticmethod
    def create_async_job(user_id, survey_id, form_data, report_type):
        """Crea el registro de la tarea en la DB y la lanza a Celery."""
        from surveys.models import Survey
        from core.models_reports import ReportJob # Asumiendo este modelo

        survey = Survey.objects.get(id=survey_id)
        
        # 1. Crear el objeto ReportJob para rastrear el progreso
        job = ReportJob.objects.create(
            user_id=user_id,
            survey=survey,
            report_type=report_type,
            status='PENDING',
            metadata={'filters': dict(form_data)}
        )

        # 2. Lanzar la tarea de Celery
        from surveys.tasks import generate_report_task 
        
        # Pasamos el ID del Job en lugar de ejecutar la lógica aquí
        generate_report_task.delay(job.id)
        
        return job

    @staticmethod
    def finalize_job(job_id, pdf_bytes, file_name):
        """
        Finaliza el ReportJob guardando el archivo y actualizando el estado.
        Esta función se llama desde la Tarea de Celery.
        """
        from core.models_reports import ReportJob
        job = ReportJob.objects.get(id=job_id)
        
        # 1. Guardar el archivo
        public_url, file_path = PDFReportGenerator._save_pdf_to_storage(pdf_bytes, file_name)
        
        # 2. Actualizar el estado del Job en la base de datos
        job.status = 'COMPLETED'
        job.file_path = file_path
        job.file_url = public_url
        job.completed_at = timezone.now()
        job.save()

        # 3. Limpiar caché si es necesario
        # (Aquí podrías agregar lógica para notificar al usuario)

        return job