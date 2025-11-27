"""
Generate test CSV file with 10,000 survey responses for performance testing.
"""
import csv
import random
from datetime import datetime

# Configuration
NUM_RESPONSES = 10000
NUM_QUESTIONS = 10
OUTPUT_FILE = 'test_10k_responses.csv'

# Sample data
IP_ADDRESSES = ['192.168.1.1', '10.0.0.1', '172.16.0.1', '8.8.8.8']
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
]

# Sample answers matching the test survey (ID=90)
QUESTION_1_OPTIONS = ['Red', 'Blue', 'Green', 'Yellow', 'Purple']
QUESTION_3_OPTIONS = ['Yes', 'No']
QUESTION_4_OPTIONS = ['Chrome', 'Firefox', 'Safari', 'Edge']
QUESTION_6_OPTIONS = ['Yes', 'No']
QUESTION_7_OPTIONS = ['18-25', '26-35', '36-45', '46-55', '56+']

print(f"Generating {NUM_RESPONSES:,} survey responses...")
start = datetime.now()

with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
    # Create header
    fieldnames = ['ip_address', 'user_agent']
    fieldnames += [f'question_{i+1}' for i in range(NUM_QUESTIONS)]
    
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    
    # Generate responses
    for i in range(NUM_RESPONSES):
        row = {
            'ip_address': random.choice(IP_ADDRESSES),
            'user_agent': random.choice(USER_AGENTS)
        }
        
        # Generate answers for each question
        for q in range(NUM_QUESTIONS):
            question_num = q + 1
            
            # Match actual survey structure (ID=90)
            if question_num == 1:
                row[f'question_{question_num}'] = random.choice(QUESTION_1_OPTIONS)
            elif question_num == 2:
                row[f'question_{question_num}'] = random.randint(1, 5)  # Rating
            elif question_num == 3:
                row[f'question_{question_num}'] = random.choice(QUESTION_3_OPTIONS)
            elif question_num == 4:
                row[f'question_{question_num}'] = random.choice(QUESTION_4_OPTIONS)
            elif question_num == 5:
                row[f'question_{question_num}'] = random.randint(1, 5)  # Rating
            elif question_num == 6:
                row[f'question_{question_num}'] = random.choice(QUESTION_6_OPTIONS)
            elif question_num == 7:
                row[f'question_{question_num}'] = random.choice(QUESTION_7_OPTIONS)
            elif question_num == 8:
                row[f'question_{question_num}'] = random.randint(1, 5)  # Rating
            else:
                # Questions 9-10 are text (no options)
                row[f'question_{question_num}'] = ''
        
        writer.writerow(row)
        
        # Progress indicator
        if (i + 1) % 1000 == 0:
            print(f'Generated {i + 1:,} rows...', end='\r')

end = datetime.now()
duration = (end - start).total_seconds()

print(f'\n✅ Generated {NUM_RESPONSES:,} responses in {duration:.2f} seconds')
print(f'   File: {OUTPUT_FILE}')
print(f'   Size: {NUM_RESPONSES * NUM_QUESTIONS:,} total answers')
print(f'\nMatching survey ID=90 structure')
print(f'Run: python manage.py import_csv_postgres {OUTPUT_FILE} --survey-id=90')
