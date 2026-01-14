from django.template.loader import render_to_string
from django.conf import settings
from weasyprint import HTML, CSS
import os


def generate_survey_pdf(survey, output_path=None):
    """
    Genera un PDF de la encuesta usando el template y CSS adaptados.
    Args:
        survey: Objeto o dict con los datos completos de la encuesta.
        output_path: Ruta donde guardar el PDF (opcional).
    Returns:
        Bytes del PDF generado si no se especifica output_path.
    """
    # Renderizar el HTML con el contexto
    html_string = render_to_string(
        'core/reports/report_document.html',
        {'survey': survey}
    )

    # Ruta absoluta al CSS
    css_path = os.path.join(settings.BASE_DIR, 'static', 'core', 'reports', 'report.css')
    css = CSS(filename=css_path)

    # Generar el PDF
    pdf = HTML(string=html_string, base_url=settings.BASE_DIR).write_pdf(stylesheets=[css])

    if output_path:
        with open(output_path, 'wb') as f:
            f.write(pdf)
        return output_path
    return pdf
