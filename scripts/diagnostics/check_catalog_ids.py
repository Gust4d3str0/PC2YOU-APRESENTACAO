import re
from pathlib import Path

with open(Path(__file__).resolve().parents[2] / 'api-catalogo/seed.py', encoding='utf-8') as f:
    text = f.read()

ids_in_seed = re.findall(r'component\(\s*\"([^\"]+)\"', text)
required = ['ram-8gb-ddr4', 'ram-16gb-ddr4', 'ram-32gb-ddr4', 'ram-8gb-ddr5', 'ram-16gb-ddr5', 'ram-32gb-ddr5', 'ram-64gb-ddr5', 'ssd-nvme-500gb', 'ssd-nvme-1tb', 'ssd-nvme-2tb', 'ssd-sata-480gb', 'ssd-sata-1tb', 'hdd-1tb', 'hdd-2tb', 'hdd-4tb', 'cooler-cm-hyper212', 'cooler-deepcool-ak400', 'cooler-deepcool-ak620', 'rtx-4060', 'rtx-4070-super', 'rtx-5090']
missing = [r for r in required if r not in ids_in_seed]
print('Missing:', missing)
