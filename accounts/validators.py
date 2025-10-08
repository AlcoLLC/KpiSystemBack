from django.core.exceptions import ValidationError

def validate_svg(file):
    if not file.name.endswith('.svg'):
        raise ValidationError("Desteklenmeyen dosya uzantısı. Yalnızca .svg kabul edilir.")
    if file.content_type != 'image/svg+xml':
         raise ValidationError("Geçersiz dosya türü.")