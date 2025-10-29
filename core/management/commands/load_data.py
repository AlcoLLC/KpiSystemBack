# Dosya: kpis/management/commands/load_data.py

import json
from django.core.management.base import BaseCommand
from kpis.models import Kpi
from accounts.models import CustomUser  # Modelinizin adı CustomUser ise

class Command(BaseCommand):
    help = 'JSON dosyasından tüm appler için veri yükler'

    def add_arguments(self, parser):
        parser.add_argument('json_file', type=str, help='İçe aktarılacak JSON dosyasının yolu')

    def handle(self, *args, **options):
        json_path = options['json_file']
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'"{json_path}" dosyası bulunamadı.'))
            return
        except json.JSONDecodeError:
            self.stdout.write(self.style.ERROR(f'"{json_path}" dosyası geçerli bir JSON değil.'))
            return

        # --- KULLANICILARI YÜKLE ---
        # "users" anahtarının JSON'da olduğundan emin olun
        if 'users' in data:
            self.stdout.write('Kullanıcılar yükleniyor...')
            for user_data in data['users']:
                try:
                    # Eğer kullanıcı zaten varsa oluşturma (hata almamak için)
                    if not CustomUser.objects.filter(username=user_data['username']).exists():
                        
                        # ÖNEMLİ: create_user veya create_superuser kullanın
                        # Bu, parolayı düz metin değil, hash'li olarak kaydeder.
                        
                        password = user_data.pop('password', 'defaultpassword123') # JSON'da parola varsa al, yoksa varsayılan ata
                        
                        # JSON'daki 'is_superuser' alanına göre karar ver
                        if user_data.get('is_superuser', False):
                            CustomUser.objects.create_superuser(
                                **user_data
                            )
                        else:
                            user = CustomUser.objects.create_user(
                                password=password,
                                **user_data
                            )
                        self.stdout.write(f"  + {user_data['username']} oluşturuldu.")
                    else:
                        self.stdout.write(f"  - {user_data['username']} zaten mevcut, atlanıyor.")
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  ! Kullanıcı yüklenirken hata: {e} - Veri: {user_data}"))
        
        # --- KPI'LARI YÜKLE (Örnek) ---
        if 'kpis' in data:
            self.stdout.write('KPI verileri yükleniyor...')
            for kpi_data in data['kpis']:
                try:
                    # Foreign Key alanları (ilişkiler) için 'id' değil, 
                    # ilgili nesneyi (object) bulup vermeniz gerekebilir.
                    # Bu kısım sizin modellerinize bağlı olarak karmaşıklaşabilir.
                    
                    # Basit bir create örneği:
                    if not Kpi.objects.filter(name=kpi_data['name']).exists():
                         Kpi.objects.create(**kpi_data)
                         self.stdout.write(f"  + KPI '{kpi_data['name']}' oluşturuldu.")
                    else:
                         self.stdout.write(f"  - KPI '{kpi_data['name']}' zaten mevcut, atlanıyor.")
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  ! KPI yüklenirken hata: {e} - Veri: {kpi_data}"))


        self.stdout.write(self.style.SUCCESS('Veri yükleme işlemi tamamlandı!'))