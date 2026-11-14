from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core_app.models import Patient, DocumentRef, Consent
from datetime import date, timedelta
from django.utils import timezone

User = get_user_model()

class Command(BaseCommand):
    help = 'Add sample documents and consents to test patient accounts'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('Adding documents and consents to patients...'))

        # Patient 1: Sarah Johnson
        try:
            user1 = User.objects.get(username='sarah.johnson')
            patient1 = Patient.objects.get(user=user1)
            
            self.stdout.write('\nAdding documents and consents for Sarah Johnson...')
            
            # Documents
            doc1, _ = DocumentRef.objects.get_or_create(
                patient=patient1,
                title="Blood Glucose Test Results",
                defaults={
                    'doc_type': 'Lab Result',
                    'uploaded_at': timezone.now() - timedelta(days=10)
                }
            )
            
            doc2, _ = DocumentRef.objects.get_or_create(
                patient=patient1,
                title="HbA1c Test - January 2025",
                defaults={
                    'doc_type': 'Lab Result',
                    'uploaded_at': timezone.now() - timedelta(days=15)
                }
            )
            
            doc3, _ = DocumentRef.objects.get_or_create(
                patient=patient1,
                title="Eye Examination Report",
                defaults={
                    'doc_type': 'Diagnostic Report',
                    'uploaded_at': timezone.now() - timedelta(days=30)
                }
            )
            
            # Consents
            consent1, _ = Consent.objects.get_or_create(
                patient=patient1,
                purpose="Insulin therapy initiation if needed",
                defaults={
                    'status': 'GRANTED',
                    'valid_from': date.today() - timedelta(days=60),
                    'valid_to': date.today() + timedelta(days=305)
                }
            )
            
            consent2, _ = Consent.objects.get_or_create(
                patient=patient1,
                purpose="Share medical records with endocrinologist",
                defaults={
                    'status': 'GRANTED',
                    'valid_from': date.today() - timedelta(days=30),
                    'valid_to': date.today() + timedelta(days=335)
                }
            )
            
            self.stdout.write(self.style.SUCCESS('✓ Sarah Johnson: 3 documents, 2 consents'))
            
        except (User.DoesNotExist, Patient.DoesNotExist):
            self.stdout.write(self.style.WARNING('⚠ Sarah Johnson not found'))

        # Patient 2: Ahmed Al-Hassan
        try:
            user2 = User.objects.get(username='ahmed.hassan')
            patient2 = Patient.objects.get(user=user2)
            
            self.stdout.write('\nAdding documents and consents for Ahmed Al-Hassan...')
            
            # Documents
            doc1, _ = DocumentRef.objects.get_or_create(
                patient=patient2,
                title="ECG - Electrocardiogram Report",
                defaults={
                    'doc_type': 'Diagnostic Report',
                    'uploaded_at': timezone.now() - timedelta(days=14)
                }
            )
            
            doc2, _ = DocumentRef.objects.get_or_create(
                patient=patient2,
                title="Cardiac Stress Test Results",
                defaults={
                    'doc_type': 'Diagnostic Report',
                    'uploaded_at': timezone.now() - timedelta(days=20)
                }
            )
            
            doc3, _ = DocumentRef.objects.get_or_create(
                patient=patient2,
                title="Cholesterol Panel - Latest",
                defaults={
                    'doc_type': 'Lab Result',
                    'uploaded_at': timezone.now() - timedelta(days=5)
                }
            )
            
            doc4, _ = DocumentRef.objects.get_or_create(
                patient=patient2,
                title="Chest X-Ray Report",
                defaults={
                    'doc_type': 'X-Ray',
                    'uploaded_at': timezone.now() - timedelta(days=45)
                }
            )
            
            # Consents
            consent1, _ = Consent.objects.get_or_create(
                patient=patient2,
                purpose="Cardiac catheterization procedure if required",
                defaults={
                    'status': 'GRANTED',
                    'valid_from': date.today() - timedelta(days=90),
                    'valid_to': date.today() + timedelta(days=275)
                }
            )
            
            consent2, _ = Consent.objects.get_or_create(
                patient=patient2,
                purpose="Emergency cardiac intervention",
                defaults={
                    'status': 'GRANTED',
                    'valid_from': date.today() - timedelta(days=90),
                    'valid_to': date.today() + timedelta(days=275)
                }
            )
            
            consent3, _ = Consent.objects.get_or_create(
                patient=patient2,
                purpose="Share records with cardiologist specialist",
                defaults={
                    'status': 'GRANTED',
                    'valid_from': date.today() - timedelta(days=60),
                    'valid_to': date.today() + timedelta(days=305)
                }
            )
            
            self.stdout.write(self.style.SUCCESS('✓ Ahmed Al-Hassan: 4 documents, 3 consents'))
            
        except (User.DoesNotExist, Patient.DoesNotExist):
            self.stdout.write(self.style.WARNING('⚠ Ahmed Al-Hassan not found'))

        # Patient 3: Layla Mahmoud
        try:
            user3 = User.objects.get(username='layla.mahmoud')
            patient3 = Patient.objects.get(user=user3)
            
            self.stdout.write('\nAdding documents and consents for Layla Mahmoud...')
            
            # Documents
            doc1, _ = DocumentRef.objects.get_or_create(
                patient=patient3,
                title="Pulmonary Function Test Results",
                defaults={
                    'doc_type': 'Diagnostic Report',
                    'uploaded_at': timezone.now() - timedelta(days=10)
                }
            )
            
            doc2, _ = DocumentRef.objects.get_or_create(
                patient=patient3,
                title="Chest X-Ray - Normal",
                defaults={
                    'doc_type': 'X-Ray',
                    'uploaded_at': timezone.now() - timedelta(days=25)
                }
            )
            
            doc3, _ = DocumentRef.objects.get_or_create(
                patient=patient3,
                title="Allergy Panel Test Results",
                defaults={
                    'doc_type': 'Lab Result',
                    'uploaded_at': timezone.now() - timedelta(days=60)
                }
            )
            
            # Consents
            consent1, _ = Consent.objects.get_or_create(
                patient=patient3,
                purpose="Emergency treatment for severe asthma attack",
                defaults={
                    'status': 'GRANTED',
                    'valid_from': date.today() - timedelta(days=180),
                    'valid_to': date.today() + timedelta(days=185)
                }
            )
            
            consent2, _ = Consent.objects.get_or_create(
                patient=patient3,
                purpose="Mental health counseling sessions",
                defaults={
                    'status': 'GRANTED',
                    'valid_from': date.today() - timedelta(days=90),
                    'valid_to': date.today() + timedelta(days=275)
                }
            )
            
            self.stdout.write(self.style.SUCCESS('✓ Layla Mahmoud: 3 documents, 2 consents'))
            
        except (User.DoesNotExist, Patient.DoesNotExist):
            self.stdout.write(self.style.WARNING('⚠ Layla Mahmoud not found'))

        self.stdout.write('\n' + '='*70)
        self.stdout.write(self.style.SUCCESS('DOCUMENTS AND CONSENTS ADDED SUCCESSFULLY!'))
        self.stdout.write('='*70)
        
        # Summary
        total_docs = DocumentRef.objects.filter(
            patient__user__username__in=['sarah.johnson', 'ahmed.hassan', 'layla.mahmoud']
        ).count()
        total_consents = Consent.objects.filter(
            patient__user__username__in=['sarah.johnson', 'ahmed.hassan', 'layla.mahmoud']
        ).count()
        
        self.stdout.write(f'\nTotal Documents: {total_docs}')
        self.stdout.write(f'Total Consents: {total_consents}')
        self.stdout.write('\n✅ All test data ready!\n')
