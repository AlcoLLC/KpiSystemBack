import os
import mimetypes
from django.core.exceptions import ValidationError

def validate_file_type(file):
    allowed_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.svg']
    allowed_mime_types = ['image/jpeg', 'image/png', 'image/webp', 'image/svg+xml']

    ext = os.path.splitext(file.name)[1].lower()
    if ext not in allowed_extensions:
        raise ValidationError(f"Desteklenmeyen dosya uzantısı: '{ext}'. İcazə verilənlər: {', '.join(allowed_extensions)}")

    mime_type, _ = mimetypes.guess_type(file.name)
    if mime_type not in allowed_mime_types:
        raise ValidationError(f"Geçersiz dosya türü: '{mime_type}'. İcazə verilənlər: {', '.join(allowed_mime_types)}")
