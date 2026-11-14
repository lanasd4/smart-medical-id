"""
Management command to populate dictionary tables with realistic medical data
Usage: python manage.py populate_dictionaries
"""

from django.core.management.base import BaseCommand
from core_app.models import ConditionDictionary, ObservationDictionary, MedicationDictionary


class Command(BaseCommand):
    help = 'Populate dictionary tables with 25 entries each'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('Starting dictionary population...'))
        
        # Populate Condition Dictionary (ICD-10 codes)
        conditions = [
            ("I10", "Essential (primary) hypertension"),
            ("E11.9", "Type 2 diabetes mellitus without complications"),
            ("J45.909", "Unspecified asthma, uncomplicated"),
            ("M79.3", "Panniculitis, unspecified"),
            ("K21.9", "Gastro-esophageal reflux disease without esophagitis"),
            ("I25.10", "Atherosclerotic heart disease of native coronary artery"),
            ("E78.5", "Hyperlipidemia, unspecified"),
            ("F41.1", "Generalized anxiety disorder"),
            ("M54.5", "Low back pain"),
            ("J06.9", "Acute upper respiratory infection, unspecified"),
            ("N39.0", "Urinary tract infection, site not specified"),
            ("R50.9", "Fever, unspecified"),
            ("J18.9", "Pneumonia, unspecified organism"),
            ("I50.9", "Heart failure, unspecified"),
            ("G43.909", "Migraine, unspecified, not intractable"),
            ("E66.9", "Obesity, unspecified"),
            ("K29.70", "Gastritis, unspecified, without bleeding"),
            ("J20.9", "Acute bronchitis, unspecified"),
            ("R51", "Headache"),
            ("M25.50", "Pain in unspecified joint"),
            ("E03.9", "Hypothyroidism, unspecified"),
            ("I63.9", "Cerebral infarction, unspecified"),
            ("N18.9", "Chronic kidney disease, unspecified"),
            ("F32.9", "Major depressive disorder, single episode, unspecified"),
            ("J44.9", "Chronic obstructive pulmonary disease, unspecified"),
        ]
        
        created_conditions = 0
        for code, name in conditions:
            obj, created = ConditionDictionary.objects.get_or_create(
                code=code,
                defaults={'name': name}
            )
            if created:
                created_conditions += 1
        
        self.stdout.write(self.style.SUCCESS(f'✓ Created {created_conditions} conditions'))
        
        # Populate Observation Dictionary (LOINC codes)
        observations = [
            ("8480-6", "Systolic blood pressure"),
            ("8462-4", "Diastolic blood pressure"),
            ("8867-4", "Heart rate"),
            ("9279-1", "Respiratory rate"),
            ("8310-5", "Body temperature"),
            ("2708-6", "Oxygen saturation"),
            ("29463-7", "Body weight"),
            ("8302-2", "Body height"),
            ("39156-5", "Body mass index (BMI)"),
            ("2345-7", "Glucose [Mass/volume] in Serum or Plasma"),
            ("2160-0", "Creatinine [Mass/volume] in Serum or Plasma"),
            ("3094-0", "Urea nitrogen [Mass/volume] in Serum or Plasma"),
            ("2951-2", "Sodium [Moles/volume] in Serum or Plasma"),
            ("2823-3", "Potassium [Moles/volume] in Serum or Plasma"),
            ("17861-6", "Calcium [Mass/volume] in Serum or Plasma"),
            ("718-7", "Hemoglobin [Mass/volume] in Blood"),
            ("26464-8", "Leukocytes [#/volume] in Blood"),
            ("777-3", "Platelets [#/volume] in Blood"),
            ("2085-9", "Cholesterol in HDL [Mass/volume] in Serum or Plasma"),
            ("2089-1", "Cholesterol in LDL [Mass/volume] in Serum or Plasma"),
            ("2571-8", "Triglyceride [Mass/volume] in Serum or Plasma"),
            ("4548-4", "Hemoglobin A1c/Hemoglobin.total in Blood"),
            ("1742-6", "Alanine aminotransferase [Enzymatic activity/volume]"),
            ("1920-8", "Aspartate aminotransferase [Enzymatic activity/volume]"),
            ("33914-3", "Glomerular filtration rate"),
        ]
        
        created_observations = 0
        for code, name in observations:
            obj, created = ObservationDictionary.objects.get_or_create(
                code=code,
                defaults={'name': name}
            )
            if created:
                created_observations += 1
        
        self.stdout.write(self.style.SUCCESS(f'✓ Created {created_observations} observations'))
        
        # Populate Medication Dictionary (RxNorm codes - common medications)
        medications = [
            ("197361", "Metformin 500 MG Oral Tablet"),
            ("314076", "Lisinopril 10 MG Oral Tablet"),
            ("197379", "Atorvastatin 20 MG Oral Tablet"),
            ("308136", "Omeprazole 20 MG Delayed Release Oral Capsule"),
            ("562251", "Amlodipine 5 MG Oral Tablet"),
            ("866924", "Aspirin 81 MG Oral Tablet"),
            ("617312", "Losartan 50 MG Oral Tablet"),
            ("197381", "Simvastatin 20 MG Oral Tablet"),
            ("313782", "Levothyroxine Sodium 0.1 MG Oral Tablet"),
            ("104080", "Albuterol 0.09 MG/ACTUAT Metered Dose Inhaler"),
            ("1049221", "Insulin Glargine 100 UNT/ML Injectable Solution"),
            ("197511", "Paracetamol 500 MG Oral Tablet"),
            ("1049502", "Amoxicillin 500 MG Oral Capsule"),
            ("1049574", "Ibuprofen 400 MG Oral Tablet"),
            ("854905", "Cetirizine 10 MG Oral Tablet"),
            ("312615", "Warfarin Sodium 5 MG Oral Tablet"),
            ("200339", "Clopidogrel 75 MG Oral Tablet"),
            ("636827", "Escitalopram 10 MG Oral Tablet"),
            ("283742", "Pantoprazole 40 MG Delayed Release Oral Tablet"),
            ("308971", "Gabapentin 300 MG Oral Capsule"),
            ("1652674", "Rosuvastatin 10 MG Oral Tablet"),
            ("351761", "Furosemide 40 MG Oral Tablet"),
            ("866511", "Metoprolol Succinate 50 MG Extended Release Tablet"),
            ("1049630", "Ciprofloxacin 500 MG Oral Tablet"),
            ("1091645", "Salbutamol 0.1 MG/ACTUAT Metered Dose Inhaler"),
        ]
        
        created_medications = 0
        for code, name in medications:
            obj, created = MedicationDictionary.objects.get_or_create(
                code=code,
                defaults={'name': name}
            )
            if created:
                created_medications += 1
        
        self.stdout.write(self.style.SUCCESS(f'✓ Created {created_medications} medications'))
        
        # Summary
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('Dictionary Population Complete!'))
        self.stdout.write(self.style.SUCCESS('='*60))
        self.stdout.write(f'Conditions: {ConditionDictionary.objects.count()} total')
        self.stdout.write(f'Observations: {ObservationDictionary.objects.count()} total')
        self.stdout.write(f'Medications: {MedicationDictionary.objects.count()} total')
        self.stdout.write(self.style.SUCCESS('='*60))
