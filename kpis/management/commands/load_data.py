# Dosya: kpis/management/commands/load_data.py

import json
from django.core.management.base import BaseCommand
from django.db import IntegrityError

# --- Tüm Gerekli Modelleri Import Ediyoruz ---
from accounts.models import User, Department, Position
from tasks.models import Task
from kpis.models import KPIEvaluation
from userkpisystem.models import UserEvaluation # Bu da aylık değerlendirmeler için

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

        # --- 1. ADIM: POZİSYONLARI YÜKLE (Bağımlılık yok) ---
        if 'positions' in data:
            self.stdout.write('Vəzifələr yüklənir...')
            for pos_data in data['positions']:
                pos, created = Position.objects.get_or_create(name=pos_data['name'])
                if created:
                    self.stdout.write(f"  + Vəzifə yaradıldı: {pos.name}")
                else:
                    self.stdout.write(f"  - Vəzifə artıq mövcuddur: {pos.name}")

        # --- 2. ADIM: DEPARTMANLARI YÜKLE (Bağımlılık yok) ---
        if 'departments' in data:
            self.stdout.write('Departamentlər yüklənir...')
            for dept_data in data['departments']:
                # manager, lead, top_management alanlarını sonra bağlayacağız
                dept_name = dept_data.get('name')
                if not dept_name:
                    continue
                dept, created = Department.objects.get_or_create(name=dept_name)
                if created:
                    self.stdout.write(f"  + Departament yaradıldı: {dept.name}")
                else:
                    self.stdout.write(f"  - Departament artıq mövcuddur: {dept.name}")

        # --- 3. ADIM: KULLANICILARI YÜKLE (Pozisyon ve Departman'a bağlı) ---
        if 'users' in data:
            self.stdout.write('İstifadəçilər yüklənir...')
            for user_data in data['users']:
                try:
                    if User.objects.filter(username=user_data['username']).exists():
                        self.stdout.write(f"  - {user_data['username']} zaten mevcut, atlanıyor.")
                        continue
                    
                    # --- İlişkileri (Foreign Key) bul ---
                    position_name = user_data.pop('position', None)
                    department_name = user_data.pop('department', None)
                    
                    position = None
                    if position_name:
                        position = Position.objects.get(name=position_name)
                        
                    department = None
                    if department_name:
                        department = Department.objects.get(name=department_name)
                    
                    password = user_data.pop('password', 'defaultpassword123')
                    
                    # --- Kullanıcıyı oluştur (superuser veya normal user) ---
                    if user_data.get('is_superuser', False):
                        User.objects.create_superuser(
                            password=password, 
                            position=position, 
                            department=department, 
                            **user_data
                        )
                    else:
                        User.objects.create_user(
                            password=password, 
                            position=position, 
                            department=department, 
                            **user_data
                        )
                    self.stdout.write(f"  + {user_data['username']} oluşturuldu.")

                except Position.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f"  ! Hata: Vəzifə tapılmadı: '{position_name}' (İstifadəçi: {user_data['username']})"))
                except Department.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f"  ! Hata: Departament tapılmadı: '{department_name}' (İstifadəçi: {user_data['username']})"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  ! Kullanıcı yüklenirken hata: {e} - Veri: {user_data}"))

        # --- 4. ADIM: DEPARTMAN YÖNETİCİLERİNİ BAĞLA (Kullanıcılar yüklendikten sonra) ---
        if 'departments' in data:
            self.stdout.write('Departament rəhbərləri bağlanır...')
            for dept_data in data['departments']:
                try:
                    dept = Department.objects.get(name=dept_data['name'])
                    
                    if 'manager' in dept_data and dept_data['manager']:
                        dept.manager = User.objects.get(username=dept_data['manager'])
                    
                    if 'department_lead' in dept_data and dept_data['department_lead']:
                        dept.department_lead = User.objects.get(username=dept_data['department_lead'])
                    
                    dept.save() # Yöneticileri kaydet

                    if 'top_management' in dept_data: # ManyToMany alanı
                        for tm_username in dept_data['top_management']:
                            tm_user = User.objects.get(username=tm_username)
                            dept.top_management.add(tm_user)
                            
                except Department.DoesNotExist:
                     self.stdout.write(self.style.ERROR(f"  ! Departament tapılmadı: {dept_data['name']}"))
                except User.DoesNotExist as e:
                     self.stdout.write(self.style.ERROR(f"  ! Rəhbər istifadəçi tapılmadı: {e}"))

        # --- 5. ADIM: TAPŞIRIQLARI (TASKS) YÜKLE (Kullanıcılara bağlı) ---
        if 'tasks' in data:
            self.stdout.write('Tapşırıqlar yüklənir...')
            for task_data in data['tasks']:
                try:
                    # JSON'da 'id' varsa ve çakışma yaratıyorsa kaldır
                    task_data.pop('id', None) 
                    
                    assignee = User.objects.get(username=task_data.pop('assignee'))
                    created_by = User.objects.get(username=task_data.pop('created_by'))
                    
                    Task.objects.create(
                        assignee=assignee,
                        created_by=created_by,
                        **task_data
                    )
                    self.stdout.write(f"  + Tapşırıq yaradıldı: {task_data['title']}")
                except User.DoesNotExist as e:
                    self.stdout.write(self.style.ERROR(f"  ! İstifadəçi tapılmadı: {e} (Tapşırıq: {task_data['title']})"))
                except IntegrityError as e:
                     self.stdout.write(self.style.ERROR(f"  ! Tapşırıq ehtimalen artıq mövcuddur: {e} - Veri: {task_data}"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  ! Tapşırıq yüklenirken hata: {e} - Veri: {task_data}"))

        # --- 6. ADIM: KPI DEĞERLENDİRMELERİNİ YÜKLE (Task ve Kullanıcılara bağlı) ---
        # JSON'da 'kpis' yerine 'kpi_evaluations' anahtarı bekliyoruz
        if 'kpi_evaluations' in data:
            self.stdout.write('KPI Değerlendirmeleri (kpis.models) yükleniyor...')
            for kpi_data in data['kpi_evaluations']:
                try:
                    # JSON'da Task'ı ID ile verdiğinizi varsayıyoruz
                    task = Task.objects.get(id=kpi_data.pop('task_id')) 
                    evaluator = User.objects.get(username=kpi_data.pop('evaluator'))
                    evaluatee = User.objects.get(username=kpi_data.pop('evaluatee'))

                    KPIEvaluation.objects.create(
                        task=task,
                        evaluator=evaluator,
                        evaluatee=evaluatee,
                        **kpi_data # self_score, superior_score vb. alanlar
                    )
                    self.stdout.write(f"  + Değerlendirme yaradıldı: {task.title}")
                
                except Task.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f"  ! Tapşırıq ID tapılmadı: {kpi_data.get('task_id')}"))
                except User.DoesNotExist as e:
                    self.stdout.write(self.style.ERROR(f"  ! İstifadəçi tapılmadı: {e} (Evaluator/Evaluatee)"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  ! KPI Değerlendirmesi yüklenirken hata: {e} - Veri: {kpi_data}"))
        
        # --- 7. ADIM: AYLIK KULLANICI DEĞERLENDİRMELERİNİ YÜKLE (Kullanıcılara bağlı) ---
        if 'user_evaluations' in data:
            self.stdout.write('Aylıq Değerlendirmeler (userkpisystem.models) yükleniyor...')
            for eval_data in data['user_evaluations']:
                try:
                    evaluator = User.objects.get(username=eval_data.pop('evaluator'))
                    evaluatee = User.objects.get(username=eval_data.pop('evaluatee'))
                    
                    UserEvaluation.objects.create(
                        evaluator=evaluator,
                        evaluatee=evaluatee,
                        **eval_data # score, comment, evaluation_date vb.
                    )
                    self.stdout.write(f"  + Aylıq Dəyərləndirmə: {evaluatee.username} ({eval_data['evaluation_date']})")
                
                except User.DoesNotExist as e:
                    self.stdout.write(self.style.ERROR(f"  ! İstifadəçi tapılmadı: {e}"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  ! Aylıq Dəyərləndirmə yüklenirken hata: {e} - Veri: {eval_data}"))


        self.stdout.write(self.style.SUCCESS('\nVeri yükleme işlemi tamamlandı!'))