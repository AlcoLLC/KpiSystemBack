# Dosya: kpis/management/commands/load_data.py

import json
from django.core.management.base import BaseCommand

# BAKIN: Hem kpis hem de accounts modellerini import ediyoruz
from kpis.models import Kpi
from accounts.models import CustomUser 
# from reports.models import Report  (Başka bir app'ten başka bir model)

class Command(BaseCommand):
    help = 'JSON dosyasından tüm appler için veri yükler'

    def add_arguments(self, parser):
        parser.add_argument('json_file', type=str, help='İçe aktarılacak JSON dosyasının yolu')

    def handle(self, *args, **options):
        with open(options['json_file'], 'r', encoding='utf-8') as f:
            data = json.load(f)

        # JSON dosyanızdaki veriye göre...
        
        # ... kpi verilerini Kpi modeline yazın
        # for kpi_data in data['kpis']:
        #     Kpi.objects.create(name=kpi_data['name'], ...)

        # ... kullanıcı verilerini CustomUser modeline yazın
        # for user_data in data['users']:
        #     CustomUser.objects.create_user(username=user_data['username'], ...)

        self.stdout.write(self.style.SUCCESS('Tüm veriler başarıyla yüklendi!'))